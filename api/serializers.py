from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import Owner, Restaurant, MenuCategory, MenuItem, Order, OrderItem


class OwnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Owner
        fields = ['id', 'name', 'email', 'phone', 'created_at']


class RegisterSerializer(serializers.Serializer):
    # Step 1: Owner details
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(min_length=6, write_only=True)
    # Step 2: Restaurant details
    restaurant_name = serializers.CharField(max_length=255)
    restaurant_type = serializers.CharField(max_length=100, default='Restaurant')
    address = serializers.CharField()
    table_count = serializers.IntegerField(default=10)

    def validate_email(self, value):
        if Owner.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def create(self, validated_data):
        owner = Owner.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            name=validated_data['name'],
            phone=validated_data['phone'],
        )
        Restaurant.objects.create(
            owner=owner,
            name=validated_data['restaurant_name'],
            restaurant_type=validated_data['restaurant_type'],
            address=validated_data['address'],
            table_count=validated_data['table_count'],
        )
        return owner


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RestaurantSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    owner_phone = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = ['id', 'name', 'restaurant_type', 'address', 'phone',
                  'description', 'logo', 'logo_url', 'qr_token', 'table_count',
                  'is_open', 'owner_name', 'owner_email', 'owner_phone']
        read_only_fields = ['qr_token', 'logo_url']

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_owner_name(self, obj):
        return obj.owner.name

    def get_owner_email(self, obj):
        return obj.owner.email

    def get_owner_phone(self, obj):
        return obj.owner.phone


class MenuCategorySerializer(serializers.ModelSerializer):
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'icon', 'sort_order', 'item_count']

    def get_item_count(self, obj):
        return obj.items.filter(is_available=True).count()


class MenuItemSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    display_image = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            'id', 'category', 'category_name', 'name', 'description',
            'price', 'image', 'image_url', 'display_image', 'is_available',
            'prep_time', 'spice_level', 'state', 'tags', 'is_popular',
            'discount_price', 'discount_until', 'is_discount_active',
            'effective_price', 'discount_percentage'
        ]

    def get_category_name(self, obj):
        return obj.category.name if obj.category else ''

    def get_display_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image_url or ''



class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'menu_item', 'name', 'price', 'quantity', 'notes', 'subtotal']

    def get_subtotal(self, obj):
        return float(obj.price) * obj.quantity


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'table_number', 'qr_type', 'customer_name',
                  'customer_notes', 'subtotal', 'tax', 'total',
                  'payment_method', 'status', 'placed_at', 'updated_at', 'items']
        read_only_fields = ['id', 'placed_at', 'updated_at']


class CreateOrderSerializer(serializers.Serializer):
    restaurant_token = serializers.CharField()
    table_number = serializers.CharField(allow_blank=True, default='')
    qr_type = serializers.ChoiceField(choices=['Table', 'Counter', 'Takeaway'], default='Table')
    customer_name = serializers.CharField(allow_blank=True, default='')
    customer_notes = serializers.CharField(allow_blank=True, default='')
    payment_method = serializers.ChoiceField(choices=['Counter', 'Online'], default='Counter')
    items = serializers.ListField(child=serializers.DictField())

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value
