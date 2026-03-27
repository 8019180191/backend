import uuid
import qrcode
import io
import base64
import traceback
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Owner, Restaurant, MenuCategory, MenuItem, Order, OrderItem, DailyAnalytics, OwnerNotification, OwnerNotificationSetting
from .utils import update_daily_stats
from .serializers import (
    RegisterSerializer, LoginSerializer, RestaurantSerializer,
    MenuCategorySerializer, MenuItemSerializer, OrderSerializer,
    CreateOrderSerializer, OwnerSerializer
)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def create_notification(restaurant, notification_type, icon, title, body):
    """Helper to create a notification for a restaurant owner. Non-fatal, respects settings."""
    try:
        # Get or create settings
        settings, _ = OwnerNotificationSetting.objects.get_or_create(restaurant=restaurant)
        
        # Check if this type of notification is enabled
        should_send = True
        if notification_type == 'new_order':
            should_send = settings.new_order_alerts
        elif notification_type == 'order_status_update':
            should_send = settings.order_status_updates
        elif notification_type == 'daily_sales_summary':
            should_send = settings.daily_sales_summary
        elif notification_type in ['combo_created', 'price_updated', 'promotion_applied']:
            should_send = settings.ai_suggestions
            
        if not should_send:
            return

        OwnerNotification.objects.create(
            restaurant=restaurant,
            notification_type=notification_type,
            icon=icon,
            title=title,
            body=body
        )
    except Exception as e:
        print(f"ERROR creating notification: {str(e)}")


def preprocess_menu_item_data(data):
    # Convert QueryDict to a mutable dict to handle list values correctly
    if hasattr(data, 'dict'):
        data = data.dict()
    else:
        data = data.copy()
    
    import json
    # Handle tags string
    if 'tags' in data:
        tags = data['tags']
        if isinstance(tags, str):
            try:
                # Try to parse as JSON first (e.g. ["Tag1", "Tag2"])
                tags_list = json.loads(tags)
                if not isinstance(tags_list, list):
                    tags_list = [str(tags_list)]
            except Exception:
                # Fallback to comma-separated list (e.g. "Tag1, Tag2")
                tags_list = [t.strip() for t in tags.split(',') if t.strip()]
            data['tags'] = tags_list

    # Handle is_available string
    if 'is_available' in data:
        val = data['is_available']
        if isinstance(val, str):
            data['is_available'] = val.lower() in ('true', '1', 'yes')
            
    return data


# ─────────────────── AUTH ───────────────────

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            # Get the first error message from the dictionary
            error_msg = next(iter(serializer.errors.values()))[0] if serializer.errors else "Registration failed"
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)
        
        owner = serializer.save()
        tokens = get_tokens_for_user(owner)
        restaurant = owner.restaurant
        return Response({
            'message': 'Account created successfully',
            'tokens': tokens,
            'owner': OwnerSerializer(owner).data,
            'restaurant_id': restaurant.id,
            'qr_token': restaurant.qr_token,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        user = authenticate(request, username=email, password=password)

        if not user:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        tokens = get_tokens_for_user(user)
        try:
            restaurant = user.restaurant
            restaurant_data = RestaurantSerializer(restaurant, context={'request': request}).data
        except Restaurant.DoesNotExist:
            restaurant_data = None

        return Response({
            'tokens': tokens,
            'owner': OwnerSerializer(user).data,
            'restaurant': restaurant_data,
        })


import random
from django.core.mail import send_mail
from django.conf import settings

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '')
        try:
            owner = Owner.objects.get(email=email)
            # Generate 6-digit OTP
            otp = str(random.randint(100000, 999999))
            owner.reset_token = otp
            owner.reset_token_expiry = timezone.now() + timedelta(minutes=10)
            owner.save()

            # Send email
            subject = 'Password Reset OTP'
            message = f'Your OTP for password reset is: {otp}. It is valid for 10 minutes.'
            email_from = settings.DEFAULT_FROM_EMAIL
            recipient_list = [email]
            
            try:
                send_mail(subject, message, email_from, recipient_list)
                return Response({'message': 'OTP sent to your email.'})
            except Exception as e:
                print(f"Error sending email: {e}")
                return Response({'error': f'Failed to send email: {str(e)}'}, status=500)
        except Owner.DoesNotExist:
            return Response({'error': 'No account found with this email.'}, status=404)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Support both Body and Query Params
        data = request.data if request.data else request.query_params
        email = str(data.get('email', '')).strip()
        otp = str(data.get('otp', '') or data.get('token', '')).strip()
        
        print(f"DEBUG: VerifyOTP Attempt - Data: {data}")
        print(f"DEBUG: Email: '{email}', OTP: '{otp}'")
        
        try:
            owner = Owner.objects.get(email=email)
            if owner.reset_token == otp:
                if owner.reset_token_expiry and owner.reset_token_expiry < timezone.now():
                    return Response({'error': 'OTP has expired.'}, status=400)
                return Response({'message': 'OTP verified successfully.'})
            else:
                return Response({'error': 'Invalid OTP.'}, status=400)
        except Owner.DoesNotExist:
            return Response({'error': 'Invalid email.'}, status=400)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Support both Body and Query Params
        data = request.data if request.data else request.query_params
        email = str(data.get('email', '')).strip()
        otp = str(data.get('otp', '') or data.get('token', '')).strip()
        new_password = str(data.get('new_password', '')).strip()
        
        print(f"DEBUG: ResetPassword Attempt - Data: {data}")
        print(f"DEBUG: Email: '{email}', OTP: '{otp}', Pass: '{new_password[:2]}...'")

        if not email or not otp or not new_password:
            return Response({'error': 'Email, OTP, and new_password are required.'}, status=400)

        if len(new_password) < 6:
            return Response({'error': 'Password must be at least 6 characters.'}, status=400)
        
        try:
            owner = Owner.objects.get(email=email)
            if owner.reset_token == otp:
                if owner.reset_token_expiry and owner.reset_token_expiry < timezone.now():
                    return Response({'error': 'OTP has expired.'}, status=400)
                
                owner.set_password(new_password)
                owner.reset_token = None
                owner.reset_token_expiry = None
                owner.save()
                return Response({'message': 'Password reset successfully.'})
            else:
                return Response({'error': 'Invalid OTP.'}, status=400)
        except Owner.DoesNotExist:
            return Response({'error': 'Invalid email.'}, status=400)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get('old_password', '')
        new_password = request.data.get('new_password', '')
        if not request.user.check_password(old_password):
            return Response({'error': 'Current password is incorrect.'}, status=400)
        if len(new_password) < 6:
            return Response({'error': 'New password must be at least 6 characters.'}, status=400)
        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': 'Password changed successfully.'})


# ─────────────────── RESTAURANT ───────────────────

class RestaurantView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        try:
            restaurant = request.user.restaurant
            serializer = RestaurantSerializer(restaurant, context={'request': request})
            return Response(serializer.data)
        except Restaurant.DoesNotExist:
            return Response({'error': 'No restaurant found.'}, status=404)

    def put(self, request):
        try:
            restaurant = request.user.restaurant
        except Restaurant.DoesNotExist:
            return Response({'error': 'No restaurant found.'}, status=404)

        # Update owner info too
        owner = request.user
        if 'owner_name' in request.data:
            owner.name = request.data['owner_name']
        if 'owner_phone' in request.data:
            owner.phone = request.data['owner_phone']
        owner.save()

        serializer = RestaurantSerializer(restaurant, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def patch(self, request):
        return self.put(request)


class RestaurantLogoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            restaurant = request.user.restaurant
        except Restaurant.DoesNotExist:
            return Response({'error': 'No restaurant found.'}, status=404)

        if 'logo' not in request.FILES:
            return Response({'error': 'No logo file provided.'}, status=400)

        restaurant.logo = request.FILES['logo']
        restaurant.save()
        logo_url = request.build_absolute_uri(restaurant.logo.url)
        return Response({'logo_url': logo_url, 'message': 'Logo updated successfully.'})


# ─────────────────── CATEGORIES ───────────────────

class CategoryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        categories = MenuCategory.objects.filter(restaurant=restaurant)
        serializer = MenuCategorySerializer(categories, many=True)
        return Response(serializer.data)

    def post(self, request):
        restaurant = request.user.restaurant
        data = request.data.copy()
        category = MenuCategory.objects.create(
            restaurant=restaurant,
            name=data.get('name', ''),
            icon=data.get('icon', '🍽️'),
            sort_order=data.get('sort_order', 0),
        )
        return Response(MenuCategorySerializer(category).data, status=201)


class CategoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, request):
        try:
            return MenuCategory.objects.get(pk=pk, restaurant=request.user.restaurant)
        except MenuCategory.DoesNotExist:
            return None

    def put(self, request, pk):
        category = self.get_object(pk, request)
        if not category:
            return Response({'error': 'Category not found.'}, status=404)
        category.name = request.data.get('name', category.name)
        category.icon = request.data.get('icon', category.icon)
        category.sort_order = request.data.get('sort_order', category.sort_order)
        category.save()
        return Response(MenuCategorySerializer(category).data)

    def delete(self, request, pk):
        category = self.get_object(pk, request)
        if not category:
            return Response({'error': 'Category not found.'}, status=404)
        category.delete()
        return Response(status=204)


# ─────────────────── MENU ITEMS ───────────────────

class MenuItemListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        items = MenuItem.objects.filter(restaurant=restaurant)
        category_id = request.query_params.get('category')
        if category_id:
            items = items.filter(category_id=category_id)
        serializer = MenuItemSerializer(items, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        try:
            # Pre-process the data to handle tags and boolean strings from Android multipart
            data = preprocess_menu_item_data(request.data)
            
            # Using the serializer for creation ensures consistent handling
            serializer = MenuItemSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                item = serializer.save(restaurant=request.user.restaurant)
                # Create notification
                create_notification(
                    request.user.restaurant, 'item_created', '🍽️',
                    'New Item Added',
                    f'"{item.name}" has been added to your menu.'
                )
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            print(f"CRITICAL ERROR in MenuItem post: {error_msg}")
            return Response({'error': str(e), 'traceback': traceback.format_exc()}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MenuItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, request):
        try:
            restaurant = getattr(request.user, 'restaurant', None)
            if not restaurant:
                return None
            return MenuItem.objects.get(pk=pk, restaurant=restaurant)
        except MenuItem.DoesNotExist:
            return None

    def get(self, request, pk):
        item = self.get_object(pk, request)
        if not item:
            return Response({'error': 'Item not found.'}, status=404)
        return Response(MenuItemSerializer(item, context={'request': request}).data)

    def put(self, request, pk):
        try:
            item = self.get_object(pk, request)
            if not item:
                return Response({'error': 'Item not found.'}, status=404)
            
            # Pre-process the data to handle tags and boolean strings from Android multipart
            data = preprocess_menu_item_data(request.data)
            
            serializer = MenuItemSerializer(item, data=data, partial=True, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"CRITICAL ERROR in MenuItem put: {error_details}")
            return Response({'error': str(e), 'details': error_details}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, pk):
        return self.put(request, pk)

    def delete(self, request, pk):
        item = self.get_object(pk, request)
        if not item:
            return Response({'error': 'Item not found.'}, status=404)
        
        try:
            item.delete()
            return Response(status=204)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class MenuItemToggleView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            item = MenuItem.objects.get(pk=pk, restaurant=request.user.restaurant)
        except MenuItem.DoesNotExist:
            return Response({'error': 'Item not found.'}, status=404)
        item.is_available = not item.is_available
        item.save()
        return Response({'id': item.id, 'is_available': item.is_available})


# ─────────────────── ORDERS (OWNER) ───────────────────

class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        qs = Order.objects.filter(restaurant=restaurant).exclude(
            status__in=['Completed', 'Cancelled']
        )
        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        serializer = OrderSerializer(qs, many=True)
        return Response(serializer.data)


class OrderHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        qs = Order.objects.filter(
            restaurant=restaurant,
            status__in=['Completed', 'Cancelled']
        )
        serializer = OrderSerializer(qs, many=True)
        return Response(serializer.data)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found.'}, status=404)
        return Response(OrderSerializer(order).data)


class OrderStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            order = Order.objects.get(pk=pk, restaurant=request.user.restaurant)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found.'}, status=404)

        new_status = request.data.get('status')
        valid_statuses = ['Received', 'Preparing', 'Ready', 'Served', 'Completed', 'Cancelled']
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of: {valid_statuses}'}, status=400)

        old_status = order.status
        order.status = new_status
        order.save()
        
        # Create notification for owner
        create_notification(
            request.user.restaurant, 'order_status_update', '📦',
            'Order Status Updated',
            f"Order #{order.id} for {order.customer_name} is now {new_status} (was {old_status})."
        )

        return Response(OrderSerializer(order).data)


# ─────────────────── ANALYTICS ───────────────────

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        now = timezone.localtime()
        today = now.date()

        # Update stats for today before showing them
        update_daily_stats(restaurant, today)
        
        stats, _ = DailyAnalytics.objects.get_or_create(restaurant=restaurant, date=today)

        # Use active orders including 'Served' status
        active_orders = Order.objects.filter(
            restaurant=restaurant,
            status__in=['Received', 'Preparing', 'Ready', 'Served']
        ).count()

        # Trending dishes (top 5 this week)
        week_ago = now - timedelta(days=7)
        trending_query = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__placed_at__gte=week_ago
        ).values('name').annotate(orders=Count('id')).order_by('-orders')
        
        top_dishes = list(trending_query[:5])
        trending_dish = top_dishes[0]['name'] if top_dishes else 'N/A'

        # More robust Today hourly orders for chart
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        today_orders = Order.objects.filter(
            restaurant=restaurant, 
            placed_at__gte=start_of_day,
            placed_at__lt=end_of_day
        )
        
        # Group by hour in Python to be timezone-safe
        order_counts = {}
        for order in today_orders:
            # Important: Use localtime of the order timestamp
            local_placed_at = timezone.localtime(order.placed_at)
            h = local_placed_at.hour
            order_counts[h] = order_counts.get(h, 0) + 1
            
        hourly_data = []
        for hour in range(24):
            display_hour = hour % 12
            if display_hour == 0: display_hour = 12
            am_pm = 'AM' if hour < 12 else 'PM'
            label = f'{display_hour} {am_pm}'
            
            hourly_data.append({
                'name': label, 
                'orders': order_counts.get(hour, 0)
            })

        # Check for Daily Sales Summary Notification (once per day)
        summary_title = f"Daily Summary - {today.strftime('%d %b %Y')}"
        if not OwnerNotification.objects.filter(restaurant=restaurant, notification_type='daily_sales_summary', title=summary_title).exists():
            today_revenue = today_orders.aggregate(Sum('total'))['total__sum'] or 0
            create_notification(
                restaurant, 'daily_sales_summary', '📊',
                summary_title,
                f"Progress so far: {today_orders.count()} orders, ₹{today_revenue} revenue."
            )

        return Response({
            'total_orders_today': today_orders.count(), 
            'revenue_today': float(stats.total_revenue) if stats.total_revenue else 0.0,
            'active_orders': active_orders,
            'trending_dish': trending_dish,
            'top_dishes': top_dishes,
            'hourly_data': hourly_data,
        })


class SalesAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        period = request.query_params.get('period', 'week')
        days = 30 if period == 'month' else 7

        now = timezone.localtime()
        
        # Ensure summary table is populated for the requested range
        for i in range(days):
            day = now.date() - timedelta(days=i)
            # We don't update EVERY time to save DB calls, just ensure it exists
            # but for simplicity in this implementation, we ensure data is fresh
            update_daily_stats(restaurant, day)

        stats = DailyAnalytics.objects.filter(
            restaurant=restaurant,
            date__gte=now.date() - timedelta(days=days-1)
        ).order_by('date')

        data = [{
            'date': item.date.strftime('%d %b'),
            'revenue': float(item.total_revenue),
            'orders': item.total_orders,
        } for item in stats]

        top_dishes = list(OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__placed_at__gte=now - timedelta(days=days)
        ).values('name').annotate(orders=Count('id')).order_by('-orders')[:5])

        return Response({
            'data': data, 
            'period': period,
            'top_dishes': top_dishes
        })


class PopularDishesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        dishes = OrderItem.objects.filter(
            order__restaurant=restaurant
        ).values('name').annotate(
            total_orders=Count('id'),
            total_revenue=Sum('price')
        ).order_by('-total_orders')[:10]

        return Response({'dishes': list(dishes)})


class PeakHoursView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        now = timezone.localtime()
        week_ago = now - timedelta(days=7)

        orders = Order.objects.filter(restaurant=restaurant, placed_at__gte=week_ago)
        order_counts = {}
        for order in orders:
            local_placed_at = timezone.localtime(order.placed_at)
            h = local_placed_at.hour
            order_counts[h] = order_counts.get(h, 0) + 1
            
        hourly_data = []
        for hour in range(0, 24):
            hourly_data.append({'hour': f'{hour:02d}:00', 'orders': order_counts.get(hour, 0)})

        return Response({'hourly_data': hourly_data})


class AIInsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        insights = []

        from .ai_utils import get_combo_suggestions, get_price_optimization_suggestions, get_promotion_suggestions
        
        # 1. Combo Opportunity Logic (Real Data)
        combo_suggs = get_combo_suggestions(restaurant)
        for combo in combo_suggs[:2]:  # Top 2 combos
            insights.append({
                'type': 'COMBO_OPPORTUNITY',
                'title': 'Combo Opportunity Detected',
                'impact': 'HIGH IMPACT',
                'description': f'"{combo["item_a_name"]}" and "{combo["item_b_name"]}" are frequently ordered together.',
                'aiSuggestion': f'Create a combo for ₹{combo["suggested_combo_price"]} (save ₹{combo["savings"]}) to increase average order value.',
                'actionLabel': 'Create Combo',
                'data': combo # Add underlying data for frontend if needed
            })

        # 2. Price Optimization Logic (Real Data)
        price_suggs = get_price_optimization_suggestions(restaurant)
        for opt in price_suggs[:2]: # Top 2 price optimizations
            insights.append({
                'type': 'PRICE_OPTIMIZATION',
                'title': 'Price Optimization',
                'impact': 'MEDIUM IMPACT',
                'description': f'"{opt["name"]}" has exceptionally high demand (ordered {opt["popularity_score"]}x average).',
                'aiSuggestion': f'Consider adjusting the price from ₹{opt["current_price"]} to ₹{opt["suggested_price"]} to increase margins.',
                'actionLabel': 'Update Price',
                'data': opt
            })

        # 3. Promotion Logic (Real Data)
        promo_suggs = get_promotion_suggestions(restaurant)
        for promo in promo_suggs[:2]: # Top 2 promotion suggestions
            if promo['type'] == 'DISCOUNT':
                suggestion = f'Offer a {promo["discount_percent"]}% discount (new price: ₹{promo["suggested_promo_price"]}) to boost sales.'
            else:
                suggestion = promo['reason']
                
            insights.append({
                'type': 'PROMOTION',
                'title': 'Promotion Suggestion',
                'impact': 'LOW IMPACT',
                'description': f'"{promo["name"]}" is struggling to get orders.',
                'aiSuggestion': suggestion,
                'actionLabel': 'Apply Promotion',
                'data': promo
            })
            
        # Fallback if no real data is available yet
        if not insights:
             insights.append({
                'type': 'PROMOTION',
                'title': 'Menu Review',
                'impact': 'LOW IMPACT',
                'description': f'We need more order data to generate accurate insights.',
                'aiSuggestion': f'Keep running your restaurant to gather more data for AI analysis!',
                'actionLabel': 'Got It'
            })

        return Response({'insights': insights})


# ─────────────────── QR CODE ───────────────────

class GenerateQRView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        host = request.build_absolute_uri('/')
        menu_url = f"{host}menu/{restaurant.qr_token}/"

        # Generate QR code image as base64
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(menu_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        return Response({
            'menu_url': menu_url,
            'qr_token': restaurant.qr_token,
            'qr_image_base64': f'data:image/png;base64,{qr_base64}',
        })


# ─────────────────── PUBLIC APIs (CUSTOMER) ───────────────────

class PublicMenuView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            restaurant = Restaurant.objects.get(qr_token=token)
        except Restaurant.DoesNotExist:
            return Response({'error': 'Restaurant not found.'}, status=404)

        categories = MenuCategory.objects.filter(restaurant=restaurant)
        items = MenuItem.objects.filter(restaurant=restaurant, is_available=True)

        return Response({
            'restaurant': {
                'id': restaurant.id,
                'name': restaurant.name,
                'type': restaurant.restaurant_type,
                'address': restaurant.address,
                'logo_url': request.build_absolute_uri(restaurant.logo.url) if restaurant.logo else None,
                'is_open': restaurant.is_open,
            },
            'categories': MenuCategorySerializer(categories, many=True).data,
            'menu_items': MenuItemSerializer(items, many=True, context={'request': request}).data,
        })


class PublicCreateOrderView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        data = serializer.validated_data
        try:
            restaurant = Restaurant.objects.get(qr_token=data['restaurant_token'])
        except Restaurant.DoesNotExist:
            return Response({'error': 'Invalid restaurant token.'}, status=404)

        # Create order
        order = Order.objects.create(
            restaurant=restaurant,
            table_number=data['table_number'],
            qr_type=data['qr_type'],
            customer_name=data['customer_name'],
            customer_notes=data['customer_notes'],
            payment_method=data['payment_method'],
            status='Received',
        )

        # Create order items
        subtotal = 0
        for item_data in data['items']:
            menu_item = None
            try:
                if 'id' in item_data:
                    menu_item = MenuItem.objects.get(id=item_data['id'], restaurant=restaurant)
            except MenuItem.DoesNotExist:
                pass

            name = item_data.get('name', menu_item.name if menu_item else 'Item')
            price = float(item_data.get('price', menu_item.price if menu_item else 0))
            quantity = int(item_data.get('quantity', 1))

            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                name=name,
                price=price,
                quantity=quantity,
                notes=item_data.get('notes', ''),
            )
            subtotal += price * quantity

        tax = round(subtotal * 0.05, 2)
        order.subtotal = subtotal
        order.tax = tax
        order.total = subtotal + tax
        order.save()

        # Create notification for the owner
        item_count = len(data['items'])
        table_info = f"Table {order.table_number}" if order.table_number else order.qr_type
        create_notification(
            restaurant, 'new_order', '🛒',
            'New Order Received',
            f'Order #{order.id} ({item_count} items, ₹{order.total}) from {table_info}.'
        )

        return Response({
            'order_id': order.id,
            'status': order.status,
            'total': float(order.total),
            'message': 'Order placed successfully!',
        }, status=201)


class PublicOrderTrackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found.'}, status=404)
        return Response(OrderSerializer(order).data)


class PublicOrderHistoryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        order_ids = request.query_params.get('ids', '')
        if not order_ids:
            return Response([])
        id_list = [i for i in order_ids.split(',') if i.isdigit()]
        orders = Order.objects.filter(id__in=id_list)
        return Response(OrderSerializer(orders, many=True).data)


# ─────────────────── NOTIFICATIONS ───────────────────

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            restaurant = request.user.restaurant
            notifications = OwnerNotification.objects.filter(restaurant=restaurant)[:50]
            data = [{
                'id': n.id,
                'notification_type': n.notification_type,
                'icon': n.icon,
                'title': n.title,
                'body': n.body,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            } for n in notifications]
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    def post(self, request):
        """Mark all read or clear all."""
        restaurant = request.user.restaurant
        action = request.data.get('action', '')
        if action == 'mark_all_read':
            OwnerNotification.objects.filter(restaurant=restaurant, is_read=False).update(is_read=True)
            return Response({'message': 'All notifications marked as read.'})
        elif action == 'clear_all':
            OwnerNotification.objects.filter(restaurant=restaurant).delete()
            return Response({'message': 'All notifications cleared.'})
        return Response({'error': 'Invalid action.'}, status=400)


class NotificationSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings, _ = OwnerNotificationSetting.objects.get_or_create(restaurant=request.user.restaurant)
        return Response({
            'new_order_alerts': settings.new_order_alerts,
            'order_status_updates': settings.order_status_updates,
            'daily_sales_summary': settings.daily_sales_summary,
            'ai_suggestions': settings.ai_suggestions,
        })

    def post(self, request):
        settings, _ = OwnerNotificationSetting.objects.get_or_create(restaurant=request.user.restaurant)
        settings.new_order_alerts = request.data.get('new_order_alerts', settings.new_order_alerts)
        settings.order_status_updates = request.data.get('order_status_updates', settings.order_status_updates)
        settings.daily_sales_summary = request.data.get('daily_sales_summary', settings.daily_sales_summary)
        settings.ai_suggestions = request.data.get('ai_suggestions', settings.ai_suggestions)
        settings.save()
        return Response({'status': 'updated'})


class NotificationDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            n = OwnerNotification.objects.get(pk=pk, restaurant=request.user.restaurant)
            n.delete()
            return Response(status=204)
        except OwnerNotification.DoesNotExist:
            return Response({'error': 'Notification not found.'}, status=404)
