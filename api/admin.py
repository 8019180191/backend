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


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'restaurant', 'table_number', 'status', 'total', 'placed_at']
    list_filter = ['status', 'restaurant']
    inlines = [OrderItemInline]


admin.site.register(Owner, OwnerAdmin)
admin.site.register(Restaurant)
admin.site.register(MenuCategory)
admin.site.register(MenuItem)
