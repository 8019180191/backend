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


SPICE_CHOICES = [('Mild', 'Mild'), ('Medium', 'Medium'), ('Hot', 'Hot'), ('Extra Hot', 'Extra Hot')]


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
    tags = models.JSONField(default=list)  # ['Veg', 'Popular']
    is_popular = models.BooleanField(default=False)
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
