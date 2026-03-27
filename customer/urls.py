from django.urls import path
from . import views

urlpatterns = [
    # QR Landing — main entry point after scanning QR
    path('<str:token>/', views.qr_landing, name='qr-landing'),
    path('<str:token>/home/', views.menu_home, name='menu-home'),
    path('<str:token>/category/<int:category_id>/', views.category_menu, name='category-menu'),
    path('<str:token>/item/<int:item_id>/', views.item_detail, name='item-detail'),
    path('<str:token>/search/', views.search, name='search'),
    path('<str:token>/cart/', views.cart, name='cart'),
    path('<str:token>/checkout/', views.checkout, name='checkout'),
    path('<str:token>/payment/<int:order_id>/', views.payment, name='payment'),
    path('<str:token>/order-confirmed/<int:order_id>/', views.order_confirmed, name='order-confirmed'),
    path('<str:token>/track/<int:order_id>/', views.order_tracking, name='order-tracking'),
    path('<str:token>/track/<int:order_id>/rate/', views.submit_rating, name='submit-rating'),
    path('<str:token>/orders/', views.order_history, name='order-history'),
    path('<str:token>/help/', views.help_support, name='help'),
    path('<str:token>/chat/', views.customer_chat, name='customer-chat'),
]
