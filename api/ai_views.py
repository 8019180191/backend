from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import MenuItem, Restaurant, Combo
from .ai_utils import get_frequent_combinations, get_price_optimization_suggestions
from .serializers import MenuItemSerializer
from .views import create_notification

class ItemRecommendationsView(APIView):
    """
    Public endpoint for customers to get suggestions when adding an item to cart.
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        # Find combinations
        suggestions = get_frequent_combinations(pk)
        
        # Get full MenuItem details for the suggestions
        item_ids = [s['menu_item_id'] for s in suggestions]
        items = MenuItem.objects.filter(id__in=item_ids)
        
        serializer = MenuItemSerializer(items, many=True, context={'request': request})
        return Response({
            'item_id': pk,
            'recommendations': serializer.data
        })

class PriceOptimizationView(APIView):
    """
    Owner endpoint to get price increase suggestions based on demand.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        restaurant = request.user.restaurant
        suggestions = get_price_optimization_suggestions(restaurant)
        return Response({'suggestions': suggestions})

class UpdateItemPriceView(APIView):
    """
    Owner endpoint to apply a suggested price increase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        restaurant = request.user.restaurant
        item = get_object_or_404(MenuItem, pk=pk, restaurant=restaurant)
        
        new_price = request.data.get('price')
        if not new_price:
            return Response({'error': 'Price is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        item.price = new_price
        item.price_optimized_count += 1
        item.save()

        # Create notification
        create_notification(
            restaurant, 'price_updated', '💰',
            'Price Updated',
            f'"{item.name}" price changed to ₹{float(item.price)}.'
        )

        return Response({
            'id': item.id,
            'name': item.name,
            'new_price': float(item.price),
            'message': 'Price updated successfully'
        })

class CreateComboView(APIView):
    """
    Owner endpoint to create a combo deal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        restaurant = request.user.restaurant
        item_a_id = request.data.get('item_a_id')
        item_b_id = request.data.get('item_b_id')
        combo_price = request.data.get('combo_price')
        name = request.data.get('name')

        if not all([item_a_id, item_b_id, combo_price]):
            return Response({'error': 'item_a_id, item_b_id, and combo_price are required'}, status=status.HTTP_400_BAD_REQUEST)

        item_a = get_object_or_404(MenuItem, pk=item_a_id, restaurant=restaurant)
        item_b = get_object_or_404(MenuItem, pk=item_b_id, restaurant=restaurant)

        if not name:
            name = f"{item_a.name} + {item_b.name} Combo"

        combo, created = Combo.objects.update_or_create(
            restaurant=restaurant,
            main_item=item_a,
            combo_item=item_b,
            defaults={
                'name': name,
                'combo_price': combo_price,
                'is_active': True
            }
        )

        # Create notification
        create_notification(
            restaurant, 'combo_created', '🌟',
            'Combo Created',
            f'"{combo.name}" combo has been created at ₹{float(combo.combo_price)}.'
        )

        return Response({
            'id': combo.id,
            'name': combo.name,
            'message': 'Combo created successfully'
        })

class ApplyPromotionView(APIView):
    """
    Owner endpoint to apply a temporary discount.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        restaurant = request.user.restaurant
        item = get_object_or_404(MenuItem, pk=pk, restaurant=restaurant)
        
        discount_price = request.data.get('discount_price')
        days = int(request.data.get('days', 2)) # Default 2 days

        if not discount_price:
            return Response({'error': 'discount_price is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        from datetime import timedelta
        
        item.discount_price = discount_price
        item.discount_until = timezone.now() + timedelta(days=days)
        item.save()

        # Create notification
        create_notification(
            restaurant, 'promotion_applied', '📣',
            'Promotion Applied',
            f'"{item.name}" discounted to ₹{float(item.discount_price)} for {days} days.'
        )

        return Response({
            'id': item.id,
            'name': item.name,
            'discount_price': float(item.discount_price),
            'discount_until': item.discount_until,
            'message': f'Promotion applied for {days} days'
        })
