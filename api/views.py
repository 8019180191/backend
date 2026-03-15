import uuid
import qrcode
import io
import base64
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Owner, Restaurant, MenuCategory, MenuItem, Order, OrderItem
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


# ─────────────────── AUTH ───────────────────

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
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
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        restaurant = request.user.restaurant
        data = request.data

        # Resolve category
        category = None
        cat_id = data.get('category') or data.get('category_id')
        if cat_id:
            try:
                category = MenuCategory.objects.get(id=cat_id, restaurant=restaurant)
            except (MenuCategory.DoesNotExist, ValueError):
                category = None

        import json
        tags = data.get('tags', [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = [t.strip() for t in tags.split(',') if t.strip()]

        # is_available comes as string "true"/"false" from Android multipart
        is_available_raw = data.get('is_available', 'true')
        if isinstance(is_available_raw, str):
            is_available = is_available_raw.lower() in ('true', '1', 'yes')
        else:
            is_available = bool(is_available_raw)

        try:
            item = MenuItem.objects.create(
                restaurant=restaurant,
                category=category,
                name=data.get('name', ''),
                description=data.get('description', ''),
                price=data.get('price', 0),
                image_url=data.get('image_url', ''),
                prep_time=data.get('prep_time', '15 mins'),
                spice_level=data.get('spice_level', 'Medium'),
                tags=tags,
                is_available=is_available,
                is_popular='Popular' in tags,
            )
            if 'image' in request.FILES:
                item.image = request.FILES['image']
                item.save()

            return Response(MenuItemSerializer(item, context={'request': request}).data, status=201)
        except Exception as e:
            return Response({'error': str(e)}, status=400)



class MenuItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, request):
        try:
            return MenuItem.objects.get(pk=pk, restaurant=request.user.restaurant)
        except MenuItem.DoesNotExist:
            return None

    def get(self, request, pk):
        item = self.get_object(pk, request)
        if not item:
            return Response({'error': 'Item not found.'}, status=404)
        return Response(MenuItemSerializer(item, context={'request': request}).data)

    def put(self, request, pk):
        item = self.get_object(pk, request)
        if not item:
            return Response({'error': 'Item not found.'}, status=404)
        data = request.data

        if 'category' in data:
            try:
                item.category = MenuCategory.objects.get(id=data['category'], restaurant=request.user.restaurant)
            except MenuCategory.DoesNotExist:
                pass

        import json
        if 'tags' in data:
            tags = data['tags']
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(',') if t.strip()]
            item.tags = tags
            item.is_popular = 'Popular' in tags

        for field in ['name', 'description', 'price', 'image_url', 'prep_time', 'spice_level', 'is_available']:
            if field in data:
                setattr(item, field, data[field])

        if 'image' in request.FILES:
            item.image = request.FILES['image']

        item.save()
        return Response(MenuItemSerializer(item, context={'request': request}).data)

    def delete(self, request, pk):
        item = self.get_object(pk, request)
        if not item:
            return Response({'error': 'Item not found.'}, status=404)
        item.delete()
        return Response(status=204)


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

        order.status = new_status
        order.save()
        return Response(OrderSerializer(order).data)


# ─────────────────── ANALYTICS ───────────────────

class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        today = timezone.now().date()

        today_orders = Order.objects.filter(restaurant=restaurant, placed_at__date=today)
        total_orders_today = today_orders.count()
        revenue_today = today_orders.filter(
            status__in=['Completed', 'Served']
        ).aggregate(total=Sum('total'))['total'] or 0

        active_orders = Order.objects.filter(
            restaurant=restaurant,
            status__in=['Received', 'Preparing', 'Ready']
        ).count()

        # Trending dish (most ordered this week)
        week_ago = timezone.now() - timedelta(days=7)
        trending = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__placed_at__gte=week_ago
        ).values('name').annotate(count=Count('id')).order_by('-count').first()
        trending_dish = trending['name'] if trending else 'N/A'

        # Today hourly orders for chart
        hourly_data = []
        for hour in range(8, 23):
            count = today_orders.filter(placed_at__hour=hour).count()
            hourly_data.append({'hour': f'{hour}:00', 'orders': count})

        return Response({
            'total_orders_today': total_orders_today,
            'revenue_today': float(revenue_today),
            'active_orders': active_orders,
            'trending_dish': trending_dish,
            'hourly_data': hourly_data,
        })


class SalesAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        period = request.query_params.get('period', 'week')

        if period == 'week':
            days = 7
        elif period == 'month':
            days = 30
        else:
            days = 7

        data = []
        for i in range(days - 1, -1, -1):
            day = timezone.now().date() - timedelta(days=i)
            orders = Order.objects.filter(
                restaurant=restaurant,
                placed_at__date=day,
                status__in=['Completed', 'Served']
            )
            revenue = orders.aggregate(total=Sum('total'))['total'] or 0
            data.append({
                'date': day.strftime('%d %b'),
                'revenue': float(revenue),
                'orders': Order.objects.filter(restaurant=restaurant, placed_at__date=day).count(),
            })

        return Response({'data': data, 'period': period})


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
        week_ago = timezone.now() - timedelta(days=7)

        hourly = []
        for hour in range(0, 24):
            count = Order.objects.filter(
                restaurant=restaurant,
                placed_at__gte=week_ago,
                placed_at__hour=hour
            ).count()
            hourly.append({'hour': f'{hour:02d}:00', 'orders': count})

        return Response({'hourly_data': hourly})


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
