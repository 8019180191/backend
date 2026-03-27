from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Owner, Restaurant, MenuCategory, MenuItem, Order, OrderItem


class OwnerAdmin(UserAdmin):
    model = Owner
    list_display = ['email', 'name', 'phone', 'is_active', 'created_at']
    list_filter = ['is_active', 'is_admin']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('name', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_admin')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'name', 'phone', 'password1', 'password2')}),
    )
    search_fields = ['email', 'name']
    ordering = ['email']
    filter_horizontal = []


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available', 'spice_level', 'state', 'is_popular']
    list_filter = ['category', 'is_available', 'spice_level', 'state', 'is_popular']
    search_fields = ['name', 'description']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'restaurant', 'table_number', 'status', 'total', 'rating', 'placed_at']
    list_filter = ['status', 'restaurant', 'rating']
    readonly_fields = ['rating', 'review_notes']
    inlines = [OrderItemInline]


admin.site.register(Owner, OwnerAdmin)
admin.site.register(Restaurant)
admin.site.register(MenuCategory)
