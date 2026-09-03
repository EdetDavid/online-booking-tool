from decimal import Decimal

import geocoder
from django.conf import settings

from .models import PriceIncrement
from .pricing import currency_amount_in_naira


class Hotel:
    def __init__(self, hotel, exchange_rate=None):
        self.hotel = hotel
        self.exchange_rate = exchange_rate

    def construct_hotel(self):
        offer = {}
        try:
            price = self.hotel['offers'][0]['price']
            price_value = price_value_naira(
                price.get('total'),
                price.get('currency', 'USD'),
                exchange_rate=self.exchange_rate,
            )
            offer['price'] = format_price_naira(
                price.get('total'),
                price.get('currency', 'USD'),
                exchange_rate=self.exchange_rate,
            )
            offer['price_value'] = price_value
            offer['name'] = self.hotel['hotel']['name']
            offer['hotelID'] = self.hotel['hotel']['hotelId']
            offer['source'] = self.hotel.get('source', 'LIVE_HOTEL_API')

            hotel_info = self.hotel['hotel']
            offer['address'] = get_hotel_address(hotel_info)
            if not offer['address']:
                address = geocoder.osm(
                    [hotel_info['latitude'], hotel_info['longitude']],
                    method='reverse',
                    timeout=settings.HOTEL_SEARCH_TIMEOUT_SECONDS,
                )
                if address and address.json:
                    if address.json.get('houseNumber') is not None:
                        offer['address'] = address.json['street'] + ' ' + address.json['houseNumber']
                    elif address.json.get('housenumber') is not None:
                        offer['address'] = address.json['street'] + ' ' + address.json['housenumber']
                    else:
                        offer['address'] = address.json.get('street', '')
        except (TypeError, AttributeError, KeyError, IndexError):
            return offer
        return offer


def get_hotel_address(hotel_info):
    address = hotel_info.get('address')
    if isinstance(address, str):
        return address
    if isinstance(address, dict):
        lines = address.get('lines') or []
        parts = [
            *lines,
            address.get('cityName', ''),
            address.get('countryCode', ''),
        ]
        return ', '.join(part for part in parts if part)
    return ''


def format_price_naira(amount, currency='USD', exchange_rate=None, markup=None):
    return f'{price_value_naira(amount, currency, exchange_rate, markup).quantize(Decimal("1")):,}'


def price_value_naira(amount, currency='USD', exchange_rate=None, markup=None):
    value = currency_amount_in_naira(amount, currency, exchange_rate)
    value += get_hotel_markup() if markup is None else Decimal(str(markup or 0))
    return value


def get_hotel_markup():
    increment = PriceIncrement.objects.first()
    if not increment:
        return Decimal('0')
    return Decimal(str(increment.increment_value or 0))
