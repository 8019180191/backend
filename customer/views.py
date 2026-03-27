from django.shortcuts import render, get_object_or_404
from django.http import Http404, JsonResponse
from api.models import Restaurant, MenuCategory, MenuItem, Order, Combo
import json


def get_restaurant_or_404(token):
    try:
        return Restaurant.objects.get(qr_token=token)
    except Restaurant.DoesNotExist:
        raise Http404("Restaurant not found")


def qr_landing(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    return render(request, 'customer/landing.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
    })


def menu_home(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    categories = MenuCategory.objects.filter(restaurant=restaurant)
    popular_items = MenuItem.objects.filter(restaurant=restaurant, is_popular=True, is_available=True)[:4]
    all_items = MenuItem.objects.filter(restaurant=restaurant, is_available=True)[:6]
    # AI picks = available items sorted by recency (mock AI)
    ai_picks = MenuItem.objects.filter(restaurant=restaurant, is_available=True)[:3]
    return render(request, 'customer/menu_home.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'categories': categories,
        'popular_items': popular_items,
        'ai_picks': ai_picks,
    })


def category_menu(request, token, category_id):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    category = get_object_or_404(MenuCategory, id=category_id, restaurant=restaurant)
    items = MenuItem.objects.filter(category=category, restaurant=restaurant, is_available=True)
    return render(request, 'customer/category_menu.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'category': category,
        'items': items,
    })


def item_detail(request, token, item_id):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    item = get_object_or_404(MenuItem, id=item_id, restaurant=restaurant)
    related = MenuItem.objects.filter(category=item.category, restaurant=restaurant, is_available=True).exclude(id=item_id)[:3]

    from django.db.models import Q
    import json
    from api.models import Combo

    # Fetch combos involving this item
    combos = Combo.objects.filter(
        Q(main_item=item) | Q(combo_item=item),
        restaurant=restaurant,
        is_active=True
    )
    
    combos_data = []
    for c in combos:
        combos_data.append({
            'id': str(c.id),
            'mainId': str(c.main_item.id),
            'mainName': c.main_item.name,
            'comboId': str(c.combo_item.id),
            'comboName': c.combo_item.name,
            'mainPrice': float(c.main_item.effective_price),
            'mainOriginalPrice': float(c.main_item.price),
            'comboItemPrice': float(c.combo_item.effective_price),
            'comboItemOriginalPrice': float(c.combo_item.price),
            'comboPrice': float(c.combo_price),
            'savings': float(c.savings),
            'image': c.combo_item.display_image,
            'mainImage': c.main_item.display_image
        })

    return render(request, 'customer/item_detail.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'item': item,
        'related': related,
        'combos_json': json.dumps(combos_data),
    })


def search(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    q = request.GET.get('q', '')
    results = []
    if q:
        results = MenuItem.objects.filter(
            restaurant=restaurant,
            is_available=True,
            name__icontains=q
        )
    return render(request, 'customer/search.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'query': q,
        'results': results,
    })


def cart(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    combos = Combo.objects.filter(restaurant=restaurant, is_active=True)
    import json
    combos_data = []
    for c in combos:
        combos_data.append({
            'id': str(c.id),
            'mainId': str(c.main_item.id),
            'mainName': c.main_item.name,
            'comboId': str(c.combo_item.id),
            'comboName': c.combo_item.name,
            'mainPrice': float(c.main_item.effective_price),
            'mainOriginalPrice': float(c.main_item.price),
            'comboItemPrice': float(c.combo_item.effective_price),
            'comboItemOriginalPrice': float(c.combo_item.price),
            'comboPrice': float(c.combo_price),
            'savings': float(c.savings),
            'image': c.combo_item.display_image,
            'mainImage': c.main_item.display_image
        })

    return render(request, 'customer/cart.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'combos_json': json.dumps(combos_data),
    })


def checkout(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    
    # Get occupied tables from active orders
    active_statuses = ['Received', 'Preparing', 'Ready', 'Served']
    active_orders = Order.objects.filter(
        restaurant=restaurant, 
        status__in=active_statuses
    ).exclude(table_number='')
    
    occupied_tables = set(active_orders.values_list('table_number', flat=True))
    
    # Generate available tables
    available_tables_data = []
    for i in range(1, restaurant.table_count + 1):
        table_str = str(i)
        # Always include the current table from URL even if it's occupied
        # so the user can add to their existing order
        if table_str not in occupied_tables or table_str == table:
            available_tables_data.append({
                'num': table_str,
                'is_selected': table_str == table
            })
            
    return render(request, 'customer/checkout.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'available_tables': available_tables_data,
    })


def payment(request, token, order_id):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    order = get_object_or_404(Order, id=order_id, restaurant=restaurant)
    return render(request, 'customer/payment.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'order': order,
    })


def order_confirmed(request, token, order_id):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    order = get_object_or_404(Order, id=order_id, restaurant=restaurant)
    return render(request, 'customer/order_confirmation.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'order': order,
    })


def order_tracking(request, token, order_id):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    order = get_object_or_404(Order, id=order_id, restaurant=restaurant)
    return render(request, 'customer/order_tracking.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'order': order,
    })


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def submit_rating(request, token, order_id):
    restaurant = get_restaurant_or_404(token)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            rating = data.get('rating')
            notes = data.get('notes', '')
            
            if rating is not None:
                order = get_object_or_404(Order, id=order_id, restaurant=restaurant)
                order.rating = int(rating)
                order.review_notes = notes
                order.save()
                return JsonResponse({'message': 'Rating submitted successfully'})
            return JsonResponse({'error': 'Rating is required'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def order_history(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    return render(request, 'customer/order_history.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
    })


def help_support(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    return render(request, 'customer/help.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
    })


@csrf_exempt
def customer_chat(request, token):
    restaurant = get_restaurant_or_404(token)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_msg = data.get('message', '').lower()
            
            # Static responses for general queries
            if 'price' in user_msg or 'how much' in user_msg:
                return JsonResponse({'response': "Prices vary by item. You can see them next to each item on the menu. Is there a specific item you're interested in?"})
            if 'offer' in user_msg or 'discount' in user_msg:
                return JsonResponse({'response': "Currently, we have some special prices on our new arrivals. Browse the 'New' section for the best deals!"})
            if 'help' in user_msg and len(user_msg) < 10:
                return JsonResponse({'response': "You can ask me about our top-rated foods, best sellers, spicy dishes, or vegetarian/non-veg options. How can I assist you today?"})

            # Feature combinations
            is_spicy = any(w in user_msg for w in ['spicy', 'spice', 'hot', 'fiery'])
            is_veg = (any(w in user_msg for w in ['veg', 'vegetarian', 'vegan']) and 'non' not in user_msg)
            is_nonveg = any(w in user_msg for w in ['non-veg', 'non veg', 'meat', 'chicken', 'beef', 'pork', 'fish'])
            is_rating = any(w in user_msg for w in ['rating', 'best rated', 'top rated', 'highest'])
            is_selling = any(w in user_msg for w in ['sell', 'favorite', 'popular', 'most ordered', 'best'])
            is_sweet = any(w in user_msg for w in ['sweet', 'dessert', 'sugar'])
            is_liquid = any(w in user_msg for w in ['liquid', 'drink', 'beverage', 'soup', 'juice'])
            is_solid = any(w in user_msg for w in ['solid', 'main course', 'dry', 'snack'])
            is_semisolid = any(w in user_msg for w in ['semi-solid', 'semi solid', 'gravy', 'curry'])
            
            # If no specific feature is asked, but they ask for menu items
            if not any([is_spicy, is_veg, is_nonveg, is_rating, is_selling, is_sweet, is_liquid, is_solid, is_semisolid]) and ('menu' in user_msg or 'food' in user_msg or 'items' in user_msg):
                items = MenuItem.objects.filter(restaurant=restaurant, is_available=True)[:5]
                names = ", ".join([item.name for item in items])
                return JsonResponse({'response': f"Sure! Here are some of our popular items: {names}. Would you like to know more about any of these?"})
            
            # If they asked for features, do dynamic filtering
            if any([is_spicy, is_veg, is_nonveg, is_rating, is_selling, is_sweet, is_liquid, is_solid, is_semisolid]):
                from django.db.models import Avg, Count
                qs = MenuItem.objects.filter(restaurant=restaurant, is_available=True).annotate(
                    avg_rating=Avg('orderitem__order__rating'),
                    order_count=Count('orderitem')
                )
                items = list(qs)
                
                if is_spicy:
                    items = [i for i in items if i.spice_level in ['Hot', 'Extra Hot']]
                
                if is_sweet:
                    items = [i for i in items if i.spice_level in ['Sweet', 'Very Sweet']]
                
                if is_liquid:
                    items = [i for i in items if i.state == 'Liquids']
                elif is_solid:
                    items = [i for i in items if i.state == 'Solids']
                elif is_semisolid:
                    items = [i for i in items if i.state == 'Semi-Solid']
                
                if is_veg:
                    items = [i for i in items if any('veg' in str(t).lower() and 'non' not in str(t).lower() for t in i.tags)]
                elif is_nonveg:
                    items = [i for i in items if any('non-veg' in str(t).lower() or 'chicken' in str(t).lower() or 'meat' in str(t).lower() for t in i.tags) or ('veg' not in [str(t).lower() for t in i.tags] and 'vegetarian' not in [str(t).lower() for t in i.tags])]
                
                if is_rating:
                    items.sort(key=lambda x: x.avg_rating or 0, reverse=True)
                elif is_selling:
                    items.sort(key=lambda x: x.order_count or 0, reverse=True)
                
                if items:
                    names = ", ".join([i.name for i in items[:4]])
                    features = []
                    if is_spicy: features.append("spicy")
                    if is_sweet: features.append("sweet")
                    if is_veg: features.append("vegetarian")
                    if is_nonveg: features.append("non-vegetarian")
                    if is_rating: features.append("top-rated")
                    if is_selling and not is_rating: features.append("best-selling")
                    if is_liquid: features.append("beverage")
                    if is_solid: features.append("solid-state")
                    if is_semisolid: features.append("gravy-based")
                    
                    desc = " ".join(features) if features else "special"
                    return JsonResponse({'response': f"Here are the perfect {desc} dishes for you: {names}."})
                else:
                    return JsonResponse({'response': "I'm sorry, I couldn't find any dishes exactly matching all those preferences together. Could you try a broader search?"})
            
            return JsonResponse({'response': "I'm here to help! Could you please tell me what you're looking for?"})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)
