from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .utils import update_daily_stats

@receiver(post_save, sender=Order)
def order_saved_handler(sender, instance, **kwargs):
    """Automatically update daily analytics when an order is created or updated."""
    update_daily_stats(instance.restaurant, instance.placed_at.date())
