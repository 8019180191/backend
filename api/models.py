import uuid
import json
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager


class OwnerManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = password  # Store as plain text
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_admin', True)
        return self.create_user(email, password, **extra_fields)


class Owner(AbstractBaseUser):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reset_token = models.CharField(max_length=100, blank=True, null=True)
    reset_token_expiry = models.DateTimeField(blank=True, null=True)

    objects = OwnerManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'owners'

    def __str__(self):
        return self.email

    @property
    def is_staff(self):
        return self.is_admin

    def has_perm(self, perm, obj=None):
        return self.is_admin

    def set_password(self, raw_password):
        self.password = raw_password

    def check_password(self, raw_password):
        return self.password == raw_password

    def has_module_perms(self, app_label):
        return self.is_admin


class Restaurant(models.Model):
    owner = models.OneToOneField(Owner, on_delete=models.CASCADE, related_name='restaurant')
    name = models.CharField(max_length=255)
    restaurant_type = models.CharField(max_length=100, default='Restaurant')
    address = models.TextField()
    phone = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)
    qr_token = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    table_count = models.IntegerField(default=10)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'restaurants'

    def __str__(self):
        return self.name

    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        return None


class MenuCategory(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, default='🍽️')
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'menu_categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return f"{self.restaurant.name} - {self.name}"


SPICE_CHOICES = [
    ('Sweet', 'Sweet'),
    ('Very Sweet', 'Very Sweet'),
    ('Mild', 'Mild'),
    ('Medium', 'Medium'),
    ('Hot', 'Hot'),
    ('Extra Hot', 'Extra Hot')
]

ITEM_STATE_CHOICES = [
    ('Solids', 'Solids'),
    ('Liquids', 'Liquids'),
    ('Semi-Solid', 'Semi-Solid'),
]


class MenuItem(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='menu_items')
    category = models.ForeignKey(MenuCategory, on_delete=models.SET_NULL, null=True, related_name='items')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    image_url = models.URLField(blank=True)  # for external URLs
    is_available = models.BooleanField(default=True)
    prep_time = models.CharField(max_length=50, default='15 mins')
    spice_level = models.CharField(max_length=20, choices=SPICE_CHOICES, default='Medium')
    state = models.CharField(max_length=20, choices=ITEM_STATE_CHOICES, default='Solids')
    tags = models.JSONField(default=list)  # ['Veg', 'Popular']
    is_popular = models.BooleanField(default=False)
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_until = models.DateTimeField(null=True, blank=True)
    price_optimized_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menu_items'
        ordering = ['category', 'name']

    def __str__(self):
        return self.name

    @property
    def display_image(self):
        if self.image:
            return self.image.url
        return self.image_url or ''

    @property
    def is_discount_active(self):
        from django.utils import timezone
        return self.discount_price and self.discount_until and self.discount_until > timezone.now()

    @property
    def effective_price(self):
        if self.is_discount_active:
            return self.discount_price
        return self.price

    @property
    def discount_percentage(self):
        if self.is_discount_active and self.price > 0:
            return round(((self.price - self.discount_price) / self.price) * 100)
        return 0


ORDER_STATUS_CHOICES = [
    ('Received', 'Received'),
    ('Preparing', 'Preparing'),
    ('Ready', 'Ready'),
    ('Served', 'Served'),
    ('Completed', 'Completed'),
    ('Cancelled', 'Cancelled'),
]

QR_TYPE_CHOICES = [('Table', 'Table'), ('Counter', 'Counter'), ('Takeaway', 'Takeaway')]
PAYMENT_CHOICES = [('Counter', 'Counter'), ('Online', 'Online')]


class Order(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='orders')
    table_number = models.CharField(max_length=20, blank=True)
    qr_type = models.CharField(max_length=20, choices=QR_TYPE_CHOICES, default='Table')
    customer_name = models.CharField(max_length=100, blank=True)
    customer_notes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='Counter')
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='Received')
    rating = models.IntegerField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-placed_at']

    def __str__(self):
        return f"ORD-{self.id} Table {self.table_number}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)  # snapshot at time of order
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'order_items'

    def __str__(self):
        return f"{self.quantity}x {self.name}"

    @property
    def subtotal(self):
        return self.price * self.quantity
class DailyAnalytics(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    total_orders = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'daily_analytics'
        unique_together = ['restaurant', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.restaurant.name} - {self.date}"


class Combo(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='combos')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    main_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='main_combos')
    combo_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='combo_addons')
    combo_price = models.DecimalField(max_digits=10, decimal_places=2)  # Discounted price for combo
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'combos'
        unique_together = ['restaurant', 'main_item', 'combo_item']

    def __str__(self):
        return f"{self.restaurant.name} - {self.main_item.name} + {self.combo_item.name}"

    @property
    def savings(self):
        return (self.main_item.price + self.combo_item.price) - self.combo_price


NOTIFICATION_TYPE_CHOICES = [
    ('new_order', 'New Order'),
    ('item_created', 'Item Created'),
    ('combo_created', 'Combo Created'),
    ('price_updated', 'Price Updated'),
    ('promotion_applied', 'Promotion Applied'),
    ('order_status_update', 'Order Status Update'),
    ('daily_sales_summary', 'Daily Sales Summary'),
]


class OwnerNotification(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    icon = models.CharField(max_length=10, default='🔔')
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'owner_notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.restaurant.name} - {self.title}"


class OwnerNotificationSetting(models.Model):
    restaurant = models.OneToOneField(Restaurant, on_delete=models.CASCADE, related_name='notification_settings')
    new_order_alerts = models.BooleanField(default=True)
    order_status_updates = models.BooleanField(default=True)
    daily_sales_summary = models.BooleanField(default=True)
    ai_suggestions = models.BooleanField(default=True)

    class Meta:
        db_table = 'owner_notification_settings'

    def __str__(self):
        return f"{self.restaurant.name} Settings"
