import os
import sys
import django

# Ensure the project root is on sys.path so menu_backend can be imported
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'menu_backend.settings')
django.setup()

from django.template.loader import render_to_string
from api.models import Restaurant, MenuCategory, MenuItem

r = Restaurant.objects.first()
cat = MenuCategory.objects.filter(restaurant=r).first()
items = MenuItem.objects.filter(category=cat, restaurant=r, is_available=True)[:1]

html = render_to_string('customer/category_menu.html', {
    'restaurant': r,
    'token': r.qr_token,
    'table': '1',
    'category': cat,
    'items': items,
})

print('Contains raw placeholder:', '{{ item.name }}' in html)
print('Sample occurrence:', html.find('{{ item.name }}'))
if '{{ item.name }}' in html:
    start = html.find('{{ item.name }}')
    print(html[start-100:start+100])
