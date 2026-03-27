from django.db.models import Sum
from django.utils import timezone
import datetime
from .models import Order, DailyAnalytics

def update_daily_stats(restaurant, date):
    """Helper to update the DailyAnalytics summary table."""
    # Use localtime to ensure we filter orders by the IST date
    # Start of day in IST as a timezone-aware UTC timestamp
    start_of_day = timezone.make_aware(datetime.datetime.combine(date, datetime.time.min))
    end_of_day = timezone.make_aware(datetime.datetime.combine(date, datetime.time.max))
    
    orders = Order.objects.filter(
        restaurant=restaurant,
        placed_at__range=(start_of_day, end_of_day)
    )
    
    total_orders = orders.count()
    total_revenue = orders.exclude(
        status='Cancelled'
    ).aggregate(total=Sum('total'))['total'] or 0.0

    DailyAnalytics.objects.update_or_create(
        restaurant=restaurant,
        date=date,
        defaults={
            'total_orders': total_orders,
            'total_revenue': total_revenue
        }
    )
