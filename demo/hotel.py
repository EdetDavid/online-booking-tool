from decimal import Decimal, InvalidOperation

import geocoder

from .models import PriceIncrement


NAIRA_PER_HOTEL_PRICE_UNIT = Decimal('1600')


class Hotel:
    def __init__(self, hotel):
        self.hotel = hotel

    def construct_hotel(self):
        offer = {}
        try:
            price = self.hotel['offers'][0]['price']
            offer['price'] = format_price_naira(
                price.get('total'),
                price.get('currency', 'USD'),
            )
            offer['name'] = self.hotel['hotel']['name']
            offer['hotelID'] = self.hotel['hotel']['hotelId']

            hotel_info = self.hotel['hotel']
            offer['address'] = get_hotel_address(hotel_info)
            if not offer['address']:
                address = geocoder.osm(
                    [hotel_info['latitude'], hotel_info['longitude']],
                    method='reverse'
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


def format_price_naira(amount, currency='USD'):
    try:
        value = Decimal(str(amount).replace(',', ''))
    except (InvalidOperation, TypeError, AttributeError):
        value = Decimal('0')

    if str(currency or '').upper() not in {'NGN', 'N', 'NAIRA'}:
        value *= NAIRA_PER_HOTEL_PRICE_UNIT

    value += get_hotel_markup()
    return f'{value.quantize(Decimal("1")):,}'


def get_hotel_markup():
    increment = PriceIncrement.objects.first()
    if not increment:
        return Decimal('0')
    return Decimal(str(increment.increment_value or 0))
