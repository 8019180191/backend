from django.shortcuts import render, get_object_or_404
from django.http import Http404
from api.models import Restaurant, MenuCategory, MenuItem, Order


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
    return render(request, 'customer/item_detail.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
        'item': item,
        'related': related,
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
    return render(request, 'customer/cart.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
    })


def checkout(request, token):
    restaurant = get_restaurant_or_404(token)
    table = request.GET.get('table', '')
    return render(request, 'customer/checkout.html', {
        'restaurant': restaurant,
        'token': token,
        'table': table,
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
