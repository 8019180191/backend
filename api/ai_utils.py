from django.db.models import Count, Sum, Avg, F, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Order, OrderItem, MenuItem, Combo


def get_frequent_combinations(menu_item_id, limit=3):
    """
    Find items frequently bought together with the given menu_item_id.
    """
    order_ids = OrderItem.objects.filter(menu_item_id=menu_item_id).values_list('order_id', flat=True)
    
    if not order_ids:
        return []

    frequent_items = OrderItem.objects.filter(
        order_id__in=order_ids
    ).exclude(
        menu_item_id=menu_item_id
    ).values(
        'menu_item_id', 'name', 'price'
    ).annotate(
        occurrence=Count('id')
    ).order_by('-occurrence')[:limit]

    return list(frequent_items)


def get_combo_suggestions(restaurant):
    """
    Suggest combo deals based on items that are frequently ordered together.
    Returns pairs of items that are commonly bought together and don't have an active combo yet.
    """
    last_30_days = timezone.now() - timedelta(days=30)
    
    # Get all orders in the last 30 days
    recent_orders = Order.objects.filter(
        restaurant=restaurant,
        placed_at__gte=last_30_days
    ).prefetch_related('items')
    
    # Count co-occurrences
    pair_counts = {}
    for order in recent_orders:
        item_ids = list(order.items.values_list('menu_item_id', flat=True))
        item_ids = [i for i in item_ids if i is not None]
        for i in range(len(item_ids)):
            for j in range(i + 1, len(item_ids)):
                pair = tuple(sorted([item_ids[i], item_ids[j]]))
                pair_counts[pair] = pair_counts.get(pair, 0) + 1
    
    if not pair_counts:
        return []
    
    # Get existing combos to avoid duplicates
    existing_combos = set(
        Combo.objects.filter(restaurant=restaurant, is_active=True)
        .values_list('main_item_id', 'combo_item_id')
    )
    existing_pairs = {tuple(sorted(pair)) for pair in existing_combos}
    
    suggestions = []
    sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
    
    for pair, count in sorted_pairs[:5]:
        if pair in existing_pairs:
            continue
        try:
            item_a = MenuItem.objects.get(id=pair[0], restaurant=restaurant)
            item_b = MenuItem.objects.get(id=pair[1], restaurant=restaurant)
            
            total_price = float(item_a.price) + float(item_b.price)
            suggested_combo_price = round(total_price * 0.88, 2)  # 12% discount
            
            suggestions.append({
                'item_a_id': item_a.id,
                'item_a_name': item_a.name,
                'item_a_price': float(item_a.price),
                'item_b_id': item_b.id,
                'item_b_name': item_b.name,
                'item_b_price': float(item_b.price),
                'ordered_together': count,
                'total_price': round(total_price, 2),
                'suggested_combo_price': suggested_combo_price,
                'savings': round(total_price - suggested_combo_price, 2),
                'reason': f"Ordered together {count} time(s) in the last 30 days."
            })
        except MenuItem.DoesNotExist:
            continue
    
    return suggestions


def get_price_optimization_suggestions(restaurant):
    """
    Identify high-demand items and suggest price increases.
    """
    last_30_days = timezone.now() - timedelta(days=30)
    
    item_stats = OrderItem.objects.filter(
        order__restaurant=restaurant,
        order__placed_at__gte=last_30_days
    ).values(
        'menu_item_id', 'name'
    ).annotate(
        total_orders=Count('id'),
        current_price=Avg('price')
    )

    if not item_stats:
        return []

    avg_orders = item_stats.aggregate(Avg('total_orders'))['total_orders__avg'] or 0
    
    suggestions = []
    for item in item_stats:
        if item['total_orders'] > (avg_orders * 1.5):
            try:
                # Fetch actual current price from MenuItem
                menu_item = MenuItem.objects.get(id=item['menu_item_id'], restaurant=restaurant)
                
                # Check optimization limit (MAX 3)
                if menu_item.price_optimized_count >= 3:
                    continue
                    
                current_price = float(menu_item.price)
                
                suggested_increase = Decimal('0.08') # 8% increase
                suggested_price = round(current_price * (1 + float(suggested_increase)), 2)
                
                # Round to nearest 5 or 9 for better pricing psychology
                if suggested_price > 100:
                    suggested_price = round(suggested_price / 5) * 5
                
                suggestions.append({
                    'id': menu_item.id,
                    'name': menu_item.name,
                    'current_price': current_price,
                    'suggested_price': suggested_price,
                    'reason': f"High Demand: Ordered {item['total_orders']} times in 30 days.",
                    'popularity_score': round(item['total_orders'] / avg_orders, 2) if avg_orders else 1
                })
            except MenuItem.DoesNotExist:
                continue
            
    return sorted(suggestions, key=lambda x: x['popularity_score'], reverse=True)


def get_promotion_suggestions(restaurant):
    """
    Suggest promotions for slow-moving or low-selling items to boost revenue.
    """
    last_30_days = timezone.now() - timedelta(days=30)
    
    # Items with order data in the last 30 days
    item_stats = OrderItem.objects.filter(
        order__restaurant=restaurant,
        order__placed_at__gte=last_30_days
    ).values(
        'menu_item_id', 'name'
    ).annotate(
        total_orders=Count('id'),
        avg_price=Avg('price')
    )

    ordered_item_ids = [i['menu_item_id'] for i in item_stats]
    avg_orders = item_stats.aggregate(Avg('total_orders'))['total_orders__avg'] or 0

    suggestions = []

    # Items with below-average orders → suggest discount promotion
    now = timezone.now()
    for item in item_stats:
        # Exclude if already has an active discount
        try:
            menu_item = MenuItem.objects.get(id=item['menu_item_id'], restaurant=restaurant)
            if menu_item.discount_until and menu_item.discount_until > now:
                continue

            if item['total_orders'] < (avg_orders * 0.5) and avg_orders > 0:
                discount = 15
                original_price = float(item['avg_price'])
                promo_price = round(original_price * (1 - discount / 100), 2)
                suggestions.append({
                    'id': item['menu_item_id'],
                    'name': item['name'],
                    'type': 'DISCOUNT',
                    'current_price': original_price,
                    'suggested_promo_price': promo_price,
                    'discount_percent': discount,
                    'reason': f"Slow seller: Only {item['total_orders']} orders in 30 days. A discount could boost visibility.",
                })
        except MenuItem.DoesNotExist:
            continue

    # Items with zero orders in 30 days → suggest "Featured Item" or free trial
    unordered_items = MenuItem.objects.filter(
        restaurant=restaurant,
        is_available=True,
        discount_until__isnull=True # No active discount
    ).exclude(id__in=ordered_item_ids) | MenuItem.objects.filter(
        restaurant=restaurant,
        is_available=True,
        discount_until__lte=now # Expired discount
    ).exclude(id__in=ordered_item_ids)

    for item in unordered_items.distinct()[:5]:
        suggestions.append({
            'id': item.id,
            'name': item.name,
            'type': 'FEATURE',
            'current_price': float(item.price),
            'suggested_promo_price': float(item.price),
            'discount_percent': 0,
            'reason': "Zero orders in 30 days. Try featuring this as a 'Chef's Special' to get attention.",
        })

    return suggestions[:8]
