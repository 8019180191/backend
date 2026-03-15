from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('auth/register/', views.RegisterView.as_view(), name='register'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/forgot-password/', views.ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/verify-otp/', views.VerifyOTPView.as_view(), name='verify-otp'),
    path('auth/reset-password/', views.ResetPasswordView.as_view(), name='reset-password'),
    path('auth/change-password/', views.ChangePasswordView.as_view(), name='change-password'),

    # Restaurant
    path('restaurant/', views.RestaurantView.as_view(), name='restaurant'),
    path('restaurant/logo/', views.RestaurantLogoView.as_view(), name='restaurant-logo'),

    # Categories
    path('categories/', views.CategoryListCreateView.as_view(), name='categories'),
    path('categories/<int:pk>/', views.CategoryDetailView.as_view(), name='category-detail'),

    # Menu Items
    path('menu-items/', views.MenuItemListCreateView.as_view(), name='menu-items'),
    path('menu-items/<int:pk>/', views.MenuItemDetailView.as_view(), name='menu-item-detail'),
    path('menu-items/<int:pk>/toggle/', views.MenuItemToggleView.as_view(), name='menu-item-toggle'),

    # Orders (Owner)
    path('orders/', views.OrderListView.as_view(), name='orders'),
    path('orders/history/', views.OrderHistoryView.as_view(), name='order-history'),
    path('orders/<int:pk>/', views.OrderDetailView.as_view(), name='order-detail'),
    path('orders/<int:pk>/status/', views.OrderStatusUpdateView.as_view(), name='order-status'),

    # Analytics
    path('analytics/dashboard/', views.DashboardStatsView.as_view(), name='analytics-dashboard'),
    path('analytics/sales/', views.SalesAnalyticsView.as_view(), name='analytics-sales'),
    path('analytics/popular/', views.PopularDishesView.as_view(), name='analytics-popular'),
    path('analytics/peak-hours/', views.PeakHoursView.as_view(), name='analytics-peak'),

    # QR Code
    path('qr/generate/', views.GenerateQRView.as_view(), name='qr-generate'),

    # Public (Customer) APIs
    path('public/menu/<str:token>/', views.PublicMenuView.as_view(), name='public-menu'),
    path('public/orders/', views.PublicCreateOrderView.as_view(), name='public-create-order'),
    path('public/orders/<int:pk>/track/', views.PublicOrderTrackView.as_view(), name='public-order-track'),
    path('public/orders/history/', views.PublicOrderHistoryView.as_view(), name='public-order-history'),
]
