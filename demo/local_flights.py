import math
from datetime import datetime, time
from decimal import Decimal
from types import SimpleNamespace

from .models import LocalFlightFare, PriceIncrement


NAIRA_PER_USD = Decimal('1600')
LOCAL_FARE_SOURCES = {'LOCAL_FARE_DB', 'SYNTHETIC_FARE_DB'}

STATIC_AIRPORTS = [
    {
        'code': 'ABV',
        'name': 'Nnamdi Azikiwe International Airport',
        'city': 'Abuja',
        'state': 'FCT',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 9.0068,
        'lon': 7.2632,
        'aliases': ('Federal Capital Territory',),
    },
    {
        'code': 'LOS',
        'name': 'Murtala Muhammed International Airport',
        'city': 'Lagos',
        'state': 'Lagos',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 6.5774,
        'lon': 3.3212,
        'aliases': ('Ikeja', 'Lagos Airport'),
    },
    {
        'code': 'PHC',
        'name': 'Port Harcourt International Airport',
        'city': 'Port Harcourt',
        'state': 'Rivers',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 5.0155,
        'lon': 6.9496,
        'aliases': ('Rivers State',),
    },
    {
        'code': 'QUO',
        'name': 'Victor Attah International Airport',
        'city': 'Uyo',
        'state': 'Akwa Ibom',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 4.8725,
        'lon': 8.0930,
        'aliases': ('Akwa Ibom Airport', 'Uyo Airport'),
    },
    {
        'code': 'KAN',
        'name': 'Mallam Aminu Kano International Airport',
        'city': 'Kano',
        'state': 'Kano',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 12.0476,
        'lon': 8.5246,
        'aliases': ('Aminu Kano',),
    },
    {
        'code': 'ENU',
        'name': 'Akanu Ibiam International Airport',
        'city': 'Enugu',
        'state': 'Enugu',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 6.4743,
        'lon': 7.5619,
        'aliases': ('Akanu Ibiam',),
    },
    {
        'code': 'CBQ',
        'name': 'Margaret Ekpo International Airport',
        'city': 'Calabar',
        'state': 'Cross River',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 4.9760,
        'lon': 8.3472,
        'aliases': ('Cross River',),
    },
    {
        'code': 'BNI',
        'name': 'Benin Airport',
        'city': 'Benin City',
        'state': 'Edo',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 6.3169,
        'lon': 5.5995,
        'aliases': ('Edo', 'Benin'),
    },
    {
        'code': 'ABB',
        'name': 'Asaba International Airport',
        'city': 'Asaba',
        'state': 'Delta',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 6.2042,
        'lon': 6.6653,
        'aliases': ('Delta State',),
    },
    {
        'code': 'QRW',
        'name': 'Osubi Airport',
        'city': 'Warri',
        'state': 'Delta',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 5.5961,
        'lon': 5.8178,
        'aliases': ('Osubi', 'Delta State'),
    },
    {
        'code': 'QOW',
        'name': 'Sam Mbakwe International Cargo Airport',
        'city': 'Owerri',
        'state': 'Imo',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 5.4271,
        'lon': 7.2060,
        'aliases': ('Imo Airport', 'Sam Mbakwe'),
    },
    {
        'code': 'AKR',
        'name': 'Akure Airport',
        'city': 'Akure',
        'state': 'Ondo',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 7.2467,
        'lon': 5.3010,
        'aliases': ('Ondo',),
    },
    {
        'code': 'IBA',
        'name': 'Ibadan Airport',
        'city': 'Ibadan',
        'state': 'Oyo',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 7.3625,
        'lon': 3.9783,
        'aliases': ('Oyo',),
    },
    {
        'code': 'ILR',
        'name': 'Ilorin International Airport',
        'city': 'Ilorin',
        'state': 'Kwara',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 8.4402,
        'lon': 4.4939,
        'aliases': ('Kwara',),
    },
    {
        'code': 'JOS',
        'name': 'Yakubu Gowon Airport',
        'city': 'Jos',
        'state': 'Plateau',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 9.6398,
        'lon': 8.8691,
        'aliases': ('Plateau',),
    },
    {
        'code': 'KAD',
        'name': 'Kaduna Airport',
        'city': 'Kaduna',
        'state': 'Kaduna',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 10.6960,
        'lon': 7.3201,
        'aliases': (),
    },
    {
        'code': 'MIU',
        'name': 'Maiduguri International Airport',
        'city': 'Maiduguri',
        'state': 'Borno',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 11.8553,
        'lon': 13.0809,
        'aliases': ('Borno',),
    },
    {
        'code': 'SKO',
        'name': 'Sultan Abubakar III International Airport',
        'city': 'Sokoto',
        'state': 'Sokoto',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 12.9163,
        'lon': 5.2072,
        'aliases': ('Sadiq Abubakar III',),
    },
    {
        'code': 'YOL',
        'name': 'Yola Airport',
        'city': 'Yola',
        'state': 'Adamawa',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 9.2576,
        'lon': 12.4304,
        'aliases': ('Adamawa',),
    },
    {
        'code': 'BCU',
        'name': 'Sir Abubakar Tafawa Balewa International Airport',
        'city': 'Bauchi',
        'state': 'Bauchi',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 10.4828,
        'lon': 9.7440,
        'aliases': ('Tafawa Balewa',),
    },
    {
        'code': 'GMO',
        'name': 'Gombe Lawanti International Airport',
        'city': 'Gombe',
        'state': 'Gombe',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 10.2983,
        'lon': 10.8964,
        'aliases': ('Lawanti',),
    },
    {
        'code': 'DKA',
        'name': "Umaru Musa Yar'adua Airport",
        'city': 'Katsina',
        'state': 'Katsina',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 13.0078,
        'lon': 7.6604,
        'aliases': ('Umaru Musa Yar Adua',),
    },
    {
        'code': 'MXJ',
        'name': 'Minna Airport',
        'city': 'Minna',
        'state': 'Niger',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 9.6522,
        'lon': 6.4623,
        'aliases': ('Niger State',),
    },
    {
        'code': 'MDI',
        'name': 'Makurdi Airport',
        'city': 'Makurdi',
        'state': 'Benue',
        'country': 'Nigeria',
        'region': 'NG',
        'lat': 7.7039,
        'lon': 8.6139,
        'aliases': ('Benue',),
    },
    {
        'code': 'ACC',
        'name': 'Kotoka International Airport',
        'city': 'Accra',
        'state': '',
        'country': 'Ghana',
        'region': 'WEST_AFRICA',
        'lat': 5.6052,
        'lon': -0.1668,
        'aliases': (),
    },
    {
        'code': 'ATL',
        'name': 'Hartsfield-Jackson Atlanta International Airport',
        'city': 'Atlanta',
        'state': 'Georgia',
        'country': 'United States',
        'region': 'NORTH_AMERICA',
        'lat': 33.6407,
        'lon': -84.4277,
        'aliases': (),
    },
    {
        'code': 'CDG',
        'name': 'Charles de Gaulle Airport',
        'city': 'Paris',
        'state': '',
        'country': 'France',
        'region': 'EUROPE',
        'lat': 49.0097,
        'lon': 2.5479,
        'aliases': (),
    },
    {
        'code': 'DOH',
        'name': 'Hamad International Airport',
        'city': 'Doha',
        'state': '',
        'country': 'Qatar',
        'region': 'MIDDLE_EAST',
        'lat': 25.2731,
        'lon': 51.6081,
        'aliases': (),
    },
    {
        'code': 'DXB',
        'name': 'Dubai International Airport',
        'city': 'Dubai',
        'state': '',
        'country': 'United Arab Emirates',
        'region': 'MIDDLE_EAST',
        'lat': 25.2532,
        'lon': 55.3657,
        'aliases': ('UAE',),
    },
    {
        'code': 'FRA',
        'name': 'Frankfurt Airport',
        'city': 'Frankfurt',
        'state': '',
        'country': 'Germany',
        'region': 'EUROPE',
        'lat': 50.0379,
        'lon': 8.5622,
        'aliases': (),
    },
    {
        'code': 'IST',
        'name': 'Istanbul Airport',
        'city': 'Istanbul',
        'state': '',
        'country': 'Turkey',
        'region': 'EUROPE',
        'lat': 41.2753,
        'lon': 28.7519,
        'aliases': (),
    },
    {
        'code': 'JFK',
        'name': 'John F. Kennedy International Airport',
        'city': 'New York',
        'state': 'New York',
        'country': 'United States',
        'region': 'NORTH_AMERICA',
        'lat': 40.6413,
        'lon': -73.7781,
        'aliases': ('NYC',),
    },
    {
        'code': 'LHR',
        'name': 'London Heathrow Airport',
        'city': 'London',
        'state': '',
        'country': 'United Kingdom',
        'region': 'EUROPE',
        'lat': 51.4700,
        'lon': -0.4543,
        'aliases': ('Heathrow', 'UK'),
    },
    {
        'code': 'NBO',
        'name': 'Jomo Kenyatta International Airport',
        'city': 'Nairobi',
        'state': '',
        'country': 'Kenya',
        'region': 'AFRICA',
        'lat': -1.3192,
        'lon': 36.9278,
        'aliases': (),
    },
    {
        'code': 'ORD',
        'name': "O'Hare International Airport",
        'city': 'Chicago',
        'state': 'Illinois',
        'country': 'United States',
        'region': 'NORTH_AMERICA',
        'lat': 41.9742,
        'lon': -87.9073,
        'aliases': ('Ohare',),
    },
    {
        'code': 'YYZ',
        'name': 'Toronto Pearson International Airport',
        'city': 'Toronto',
        'state': 'Ontario',
        'country': 'Canada',
        'region': 'NORTH_AMERICA',
        'lat': 43.6777,
        'lon': -79.6248,
        'aliases': ('Pearson',),
    },
    {
        'code': 'NRT',
        'name': 'Narita International Airport',
        'city': 'Tokyo',
        'state': '',
        'country': 'Japan',
        'region': 'ASIA',
        'lat': 35.7719,
        'lon': 140.3929,
        'aliases': (),
    },
    {
        'code': 'HND',
        'name': 'Tokyo Haneda Airport',
        'city': 'Tokyo',
        'state': '',
        'country': 'Japan',
        'region': 'ASIA',
        'lat': 35.5494,
        'lon': 139.7798,
        'aliases': ('Haneda',),
    },
]

AIRPORT_LOOKUP = {airport['code']: airport for airport in STATIC_AIRPORTS}
AIRPORT_NAMES = {
    airport['code']: airport['name']
    for airport in STATIC_AIRPORTS
}
AIRPORT_META = {
    airport['code']: {
        'region': airport['region'],
        'lat': airport['lat'],
        'lon': airport['lon'],
    }
    for airport in STATIC_AIRPORTS
}

DEFAULT_AIRLINES = {
    'NG': ('P4', 'Air Peace'),
    'WEST_AFRICA': ('AW', 'Africa World'),
    'MIDDLE_EAST': ('QR', 'Qatar Airways'),
    'EUROPE': ('BA', 'British Airways'),
    'NORTH_AMERICA': ('DL', 'Delta Air Lines'),
    'AFRICA': ('KQ', 'Kenya Airways'),
    'ASIA': ('QR', 'Qatar Airways'),
    'UNKNOWN': ('P4', 'Air Peace'),
}

LOCAL_RESULTS_TARGET = 18

SYNTHETIC_AIRLINES = {
    'NG': [
        ('P4', 'Air Peace'),
        ('Q9', 'Green Africa'),
        ('QI', 'Ibom Air'),
        ('VK', 'ValueJet'),
        ('W3', 'Arik Air'),
        ('OF', 'Overland Airways'),
        ('R2', 'Rano Air'),
        ('NU', 'United Nigeria'),
    ],
    'WEST_AFRICA': [
        ('AW', 'Africa World'),
        ('P4', 'Air Peace'),
        ('KP', 'ASKY Airlines'),
        ('HF', "Air Cote d'Ivoire"),
    ],
    'AFRICA': [
        ('ET', 'Ethiopian Airlines'),
        ('KQ', 'Kenya Airways'),
        ('WB', 'RwandAir'),
        ('MS', 'EgyptAir'),
        ('P4', 'Air Peace'),
    ],
    'MIDDLE_EAST': [
        ('QR', 'Qatar Airways'),
        ('EK', 'Emirates'),
        ('TK', 'Turkish Airlines'),
        ('ET', 'Ethiopian Airlines'),
    ],
    'EUROPE': [
        ('BA', 'British Airways'),
        ('VS', 'Virgin Atlantic'),
        ('LH', 'Lufthansa'),
        ('AF', 'Air France'),
        ('KL', 'KLM'),
        ('TK', 'Turkish Airlines'),
        ('QR', 'Qatar Airways'),
    ],
    'NORTH_AMERICA': [
        ('DL', 'Delta Air Lines'),
        ('UA', 'United Airlines'),
        ('BA', 'British Airways'),
        ('VS', 'Virgin Atlantic'),
        ('QR', 'Qatar Airways'),
        ('TK', 'Turkish Airlines'),
        ('ET', 'Ethiopian Airlines'),
    ],
    'ASIA': [
        ('QR', 'Qatar Airways'),
        ('EK', 'Emirates'),
        ('TK', 'Turkish Airlines'),
        ('ET', 'Ethiopian Airlines'),
    ],
}

SYNTHETIC_VARIANTS = [
    {'multiplier': Decimal('0.86'), 'depart': time(5, 45), 'return_depart': time(7, 20), 'duration_offset': -8, 'seats': 4, 'can_stop': False},
    {'multiplier': Decimal('0.91'), 'depart': time(6, 30), 'return_depart': time(8, 35), 'duration_offset': -4, 'seats': 7, 'can_stop': False},
    {'multiplier': Decimal('0.96'), 'depart': time(7, 25), 'return_depart': time(9, 40), 'duration_offset': 0, 'seats': 9, 'can_stop': False},
    {'multiplier': Decimal('1.02'), 'depart': time(8, 50), 'return_depart': time(10, 25), 'duration_offset': 8, 'seats': 6, 'can_stop': True},
    {'multiplier': Decimal('0.94'), 'depart': time(10, 15), 'return_depart': time(12, 10), 'duration_offset': -2, 'seats': 5, 'can_stop': False},
    {'multiplier': Decimal('1.08'), 'depart': time(11, 35), 'return_depart': time(13, 45), 'duration_offset': 12, 'seats': 8, 'can_stop': True},
    {'multiplier': Decimal('1.00'), 'depart': time(13, 5), 'return_depart': time(15, 15), 'duration_offset': 0, 'seats': 9, 'can_stop': False},
    {'multiplier': Decimal('1.12'), 'depart': time(14, 30), 'return_depart': time(16, 30), 'duration_offset': 16, 'seats': 3, 'can_stop': True},
    {'multiplier': Decimal('1.05'), 'depart': time(15, 45), 'return_depart': time(17, 40), 'duration_offset': 6, 'seats': 6, 'can_stop': False},
    {'multiplier': Decimal('1.18'), 'depart': time(17, 10), 'return_depart': time(18, 55), 'duration_offset': 18, 'seats': 5, 'can_stop': True},
    {'multiplier': Decimal('1.10'), 'depart': time(18, 25), 'return_depart': time(20, 15), 'duration_offset': 10, 'seats': 8, 'can_stop': False},
    {'multiplier': Decimal('1.24'), 'depart': time(20, 5), 'return_depart': time(21, 35), 'duration_offset': 24, 'seats': 4, 'can_stop': True},
    {'multiplier': Decimal('0.89'), 'depart': time(21, 45), 'return_depart': time(6, 50), 'duration_offset': 4, 'seats': 9, 'can_stop': False},
    {'multiplier': Decimal('1.31'), 'depart': time(23, 15), 'return_depart': time(22, 20), 'duration_offset': 30, 'seats': 2, 'can_stop': True},
]


def normalize_iata(value):
    if not value:
        return ''
    return value.split(',', 1)[0].strip().upper()[:3]


def normalize_cabin(value):
    if not value:
        return 'ECONOMY'
    return value.strip().upper().replace('-', '_')


def local_flight_search(origin, destination, departure_date, return_date=None, passenger_count=1, cabin='ECONOMY'):
    origin = normalize_iata(origin)
    destination = normalize_iata(destination)
    cabin = normalize_cabin(cabin)
    passenger_count = int(passenger_count or 1)

    fares = find_matching_fares(origin, destination, cabin, passenger_count)
    reverse_route = False

    if not fares.exists() and cabin != 'ECONOMY':
        fares = find_matching_fares(origin, destination, 'ECONOMY', passenger_count)

    if not fares.exists():
        fares = find_matching_fares(destination, origin, cabin, passenger_count)
        reverse_route = fares.exists()

    if not fares.exists() and cabin != 'ECONOMY':
        fares = find_matching_fares(destination, origin, 'ECONOMY', passenger_count)
        reverse_route = fares.exists()

    offers = []
    if fares.exists():
        offers = [
            build_local_offer(
            fare,
            departure_date,
            return_date,
            passenger_count,
            requested_origin=origin,
            requested_destination=destination,
            reverse_route=reverse_route,
            )
            for fare in fares[:LOCAL_RESULTS_TARGET]
        ]

    if len(offers) < LOCAL_RESULTS_TARGET:
        synthetic_offers = build_synthetic_offers(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passenger_count=passenger_count,
            cabin=cabin,
            max_offers=LOCAL_RESULTS_TARGET - len(offers),
            id_offset=len(offers),
        )
        existing_ids = {offer['id'] for offer in offers}
        offers.extend(
            offer for offer in synthetic_offers
            if offer['id'] not in existing_ids
        )

    return offers[:LOCAL_RESULTS_TARGET]


def find_matching_fares(origin, destination, cabin, passenger_count):
    return LocalFlightFare.objects.filter(
        origin=origin,
        destination=destination,
        cabin=cabin,
        active=True,
        seats_available__gte=passenger_count,
    )


def local_airport_search(term=''):
    term = (term or '').strip().upper()
    codes = set(AIRPORT_NAMES.keys())

    try:
        for origin, destination, stop_airport in LocalFlightFare.objects.filter(active=True).values_list(
            'origin',
            'destination',
            'stop_airport',
        ):
            codes.add(origin)
            codes.add(destination)
            if stop_airport:
                codes.add(stop_airport)
    except Exception:
        pass

    results = []
    for code in sorted(filter(None, codes)):
        label = airport_label(code)
        if not term or term in airport_search_text(code, label):
            results.append(label)

    return results


def airport_label(code):
    airport = AIRPORT_LOOKUP.get(code)
    if not airport:
        return f'{code}, {AIRPORT_NAMES.get(code, code)}'

    city_country = airport['city']
    if airport.get('state') and airport['state'] != airport['city']:
        city_country = f"{city_country}, {airport['state']}"
    city_country = f"{city_country}, {airport['country']}"
    return f"{code}, {airport['name']} - {city_country}"


def airport_search_text(code, label):
    airport = AIRPORT_LOOKUP.get(code, {})
    parts = [
        code,
        label,
        airport.get('name', ''),
        airport.get('city', ''),
        airport.get('state', ''),
        airport.get('country', ''),
        *airport.get('aliases', ()),
    ]
    return ' '.join(parts).upper()


def build_local_offer(fare, departure_date, return_date, passenger_count, requested_origin=None, requested_destination=None, reverse_route=False):
    price_usd_equivalent = (Decimal(fare.base_price_naira) * passenger_count) / NAIRA_PER_USD
    outbound_origin = requested_origin or fare.origin
    outbound_destination = requested_destination or fare.destination
    return_origin = outbound_destination
    return_destination = outbound_origin
    outbound_departure_time = fare.departure_time
    outbound_arrival_time = fare.arrival_time
    inbound_departure_time = fare.return_departure_time or fare.departure_time
    inbound_arrival_time = fare.return_arrival_time or fare.arrival_time

    if reverse_route:
        outbound_departure_time = fare.return_departure_time or fare.departure_time
        outbound_arrival_time = fare.return_arrival_time or fare.arrival_time
        inbound_departure_time = fare.departure_time
        inbound_arrival_time = fare.arrival_time

    offer = {
        'id': f'LOCAL-{fare.id}-{departure_date}-{return_date or "OW"}',
        'source': 'LOCAL_FARE_DB',
        'numberOfBookableSeats': fare.seats_available,
        'price': {
            'currency': 'USD',
            'total': f'{price_usd_equivalent:.2f}',
        },
        'travelerPricings': [
            {
                'travelerId': str(index + 1),
                'fareDetailsBySegment': [{'cabin': fare.cabin}],
            }
            for index in range(passenger_count)
        ],
        'itineraries': [
            build_itinerary(
                origin=outbound_origin,
                destination=outbound_destination,
                date_value=departure_date,
                depart_time=outbound_departure_time,
                arrive_time=outbound_arrival_time,
                airline_code=fare.airline_code,
                duration=fare.flight_duration,
                stop_airport=fare.stop_airport,
            )
        ],
    }

    if return_date:
        offer['itineraries'].append(
            build_itinerary(
                origin=return_origin,
                destination=return_destination,
                date_value=return_date,
                depart_time=inbound_departure_time,
                arrive_time=inbound_arrival_time,
                airline_code=fare.airline_code,
                duration=fare.return_duration or fare.flight_duration,
                stop_airport=fare.stop_airport,
            )
        )

    return offer


def build_synthetic_offers(origin, destination, departure_date, return_date, passenger_count, cabin, max_offers=LOCAL_RESULTS_TARGET, id_offset=0):
    base_price = estimate_route_price(origin, destination, cabin)
    airlines = synthetic_airline_options(origin, destination)
    base_duration = estimate_duration(origin, destination)

    offers = []
    for position in range(max_offers):
        sequence = id_offset + position + 1
        variant = SYNTHETIC_VARIANTS[(sequence - 1) % len(SYNTHETIC_VARIANTS)]
        airline_code, airline_name = airlines[(sequence - 1) % len(airlines)]
        cycle = (sequence - 1) // len(SYNTHETIC_VARIANTS)
        depart_time = time_with_offset(variant['depart'], cycle * 11)
        return_depart_time = time_with_offset(variant['return_depart'], cycle * 13)
        duration = duration_with_offset(base_duration, variant['duration_offset'])
        stop_airport = synthetic_stop_airport(
            origin,
            destination,
            variant_index=sequence,
            airline_code=airline_code,
        ) if variant['can_stop'] else ''
        price_multiplier = variant['multiplier'] + (Decimal(cycle) * Decimal('0.035'))
        price = (base_price * price_multiplier).quantize(Decimal('1000'))
        arrive_time = arrival_time_for(depart_time, duration)
        fare = SimpleNamespace(
            id=f'SYN-{origin}-{destination}-{sequence}',
            origin=origin,
            destination=destination,
            airline_code=airline_code,
            airline_name=airline_name,
            cabin=cabin if cabin in dict(LocalFlightFare.CABIN_CHOICES) else 'ECONOMY',
            base_price_naira=price,
            departure_time=depart_time,
            arrival_time=arrive_time,
            return_departure_time=return_depart_time,
            return_arrival_time=arrival_time_for(return_depart_time, duration),
            stop_airport=stop_airport,
            flight_duration=duration,
            return_duration=duration,
            seats_available=max(int(variant['seats']), passenger_count),
        )
        offer = build_local_offer(
            fare,
            departure_date,
            return_date,
            passenger_count,
            requested_origin=origin,
            requested_destination=destination,
        )
        offer['source'] = 'SYNTHETIC_FARE_DB'
        offers.append(offer)

    return offers


def synthetic_airline_options(origin, destination):
    origin_region = get_airport_region(origin)
    destination_region = get_airport_region(destination)
    if origin_region == 'NG' and destination_region == 'NG':
        return SYNTHETIC_AIRLINES['NG']

    route_region = get_route_region(origin, destination)
    return SYNTHETIC_AIRLINES.get(
        route_region,
        [DEFAULT_AIRLINES.get(route_region, DEFAULT_AIRLINES['UNKNOWN'])]
    )


def estimate_route_price(origin, destination, cabin):
    origin_region = get_airport_region(origin)
    destination_region = get_airport_region(destination)
    distance = estimate_distance_km(origin, destination)

    if origin_region == 'NG' and destination_region == 'NG':
        price = Decimal('120000') + Decimal(distance * 80)
    elif {origin_region, destination_region} <= {'NG', 'WEST_AFRICA', 'AFRICA'}:
        price = Decimal('260000') + Decimal(distance * 95)
    elif 'MIDDLE_EAST' in {origin_region, destination_region}:
        price = Decimal('760000') + Decimal(distance * 55)
    elif 'EUROPE' in {origin_region, destination_region}:
        price = Decimal('930000') + Decimal(distance * 58)
    elif 'NORTH_AMERICA' in {origin_region, destination_region}:
        price = Decimal('1350000') + Decimal(distance * 65)
    else:
        price = Decimal('550000') + Decimal(distance * 75)

    cabin_multiplier = {
        'ECONOMY': Decimal('1.0'),
        'PREMIUM_ECONOMY': Decimal('1.55'),
        'BUSINESS': Decimal('2.65'),
        'FIRST': Decimal('4.20'),
    }.get(normalize_cabin(cabin), Decimal('1.0'))

    return (price * cabin_multiplier).quantize(Decimal('1000'))


def get_route_region(origin, destination):
    destination_region = get_airport_region(destination)
    if destination_region != 'UNKNOWN':
        return destination_region
    return get_airport_region(origin)


def get_airport_region(code):
    return AIRPORT_META.get(code, {}).get('region', 'UNKNOWN')


def estimate_distance_km(origin, destination):
    origin_meta = AIRPORT_META.get(origin)
    destination_meta = AIRPORT_META.get(destination)
    if not origin_meta or not destination_meta:
        return 5000

    lat1, lon1 = math.radians(origin_meta['lat']), math.radians(origin_meta['lon'])
    lat2, lon2 = math.radians(destination_meta['lat']), math.radians(destination_meta['lon'])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return int(6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def estimate_duration(origin, destination):
    distance = estimate_distance_km(origin, destination)
    minutes = max(70, int((distance / 760) * 60) + 45)
    hours = minutes // 60
    mins = minutes % 60
    return f'PT{hours}H{mins:02d}M'


def duration_to_minutes(duration):
    if not duration:
        return 75
    value = duration.replace('PT', '')
    hours = 0
    minutes = 0
    if 'H' in value:
        hours_part, value = value.split('H', 1)
        hours = int(hours_part or 0)
    if 'M' in value:
        minutes = int(value.split('M', 1)[0] or 0)
    return hours * 60 + minutes


def minutes_to_duration(minutes):
    minutes = max(35, int(minutes))
    hours = minutes // 60
    mins = minutes % 60
    return f'PT{hours}H{mins:02d}M'


def duration_with_offset(duration, minute_offset):
    return minutes_to_duration(duration_to_minutes(duration) + minute_offset)


def time_with_offset(time_value, minute_offset):
    total_minutes = (time_value.hour * 60 + time_value.minute + minute_offset) % (24 * 60)
    return time(total_minutes // 60, total_minutes % 60)


def arrival_time_for(depart_time, duration):
    return time_with_offset(depart_time, duration_to_minutes(duration))


def synthetic_stop_airport(origin, destination, variant_index=0, airline_code=''):
    origin_region = get_airport_region(origin)
    destination_region = get_airport_region(destination)
    distance = estimate_distance_km(origin, destination)
    if origin_region == 'NG' and destination_region == 'NG':
        if variant_index % 5 != 0:
            return ''
        for stop in ('ABV', 'LOS', 'PHC'):
            if stop not in {origin, destination}:
                return stop
        return ''

    if distance < 1800 and variant_index % 4 != 0:
        return ''

    airline_hubs = {
        'AF': 'CDG',
        'AW': 'ACC',
        'BA': 'LHR',
        'DL': 'JFK',
        'EK': 'DXB',
        'ET': 'ADD',
        'HF': 'ABJ',
        'KL': 'AMS',
        'KP': 'LFW',
        'KQ': 'NBO',
        'LH': 'FRA',
        'MS': 'CAI',
        'QR': 'DOH',
        'TK': 'IST',
        'UA': 'ORD',
        'VS': 'LHR',
        'WB': 'KGL',
    }
    stop = airline_hubs.get(airline_code)
    if stop and stop not in {origin, destination}:
        if distance > 4500 or variant_index % 3 == 0:
            return stop

    if distance < 4500:
        for stop in ('ABV', 'LOS', 'ACC'):
            if stop not in {origin, destination}:
                return stop
        return ''
    if 'MIDDLE_EAST' in {origin_region, destination_region}:
        stop = 'DOH'
        return '' if stop in {origin, destination} else stop
    if 'EUROPE' in {origin_region, destination_region} and origin not in {'LHR', 'CDG', 'FRA', 'IST'} and destination not in {'LHR', 'CDG', 'FRA', 'IST'}:
        stop = 'LHR'
        return '' if stop in {origin, destination} else stop
    if 'NORTH_AMERICA' in {origin_region, destination_region}:
        stop = 'LHR'
        return '' if stop in {origin, destination} else stop
    return ''


def build_itinerary(origin, destination, date_value, depart_time, arrive_time, airline_code, duration, stop_airport=''):
    departure_at = combine_date_time(date_value, depart_time)
    arrival_at = combine_date_time(date_value, arrive_time)

    if stop_airport:
        total_minutes = duration_to_minutes(duration)
        connection_minutes = min(120, max(45, total_minutes // 7))
        flight_minutes = max(70, total_minutes - connection_minutes)
        first_minutes = max(35, int(flight_minutes * Decimal('0.45')))
        second_minutes = max(35, flight_minutes - first_minutes)
        first_arrival = combine_date_time(date_value, depart_time, minute_offset=first_minutes)
        second_departure = combine_date_time(date_value, depart_time, minute_offset=first_minutes + connection_minutes)
        arrival_at = combine_date_time(date_value, depart_time, minute_offset=first_minutes + connection_minutes + second_minutes)
        return {
            'duration': duration,
            'segments': [
                {
                    'departure': {'iataCode': origin, 'at': departure_at},
                    'arrival': {'iataCode': stop_airport, 'at': first_arrival},
                    'carrierCode': airline_code,
                    'duration': minutes_to_duration(first_minutes),
                },
                {
                    'departure': {'iataCode': stop_airport, 'at': second_departure},
                    'arrival': {'iataCode': destination, 'at': arrival_at},
                    'carrierCode': airline_code,
                    'duration': minutes_to_duration(second_minutes),
                },
            ],
        }

    return {
        'duration': duration,
        'segments': [
            {
                'departure': {'iataCode': origin, 'at': departure_at},
                'arrival': {'iataCode': destination, 'at': arrival_at},
                'carrierCode': airline_code,
                'duration': duration,
            }
        ],
    }


def combine_date_time(date_value, time_value, hour_offset=0, minute_offset=0):
    date_part = datetime.strptime(date_value, '%Y-%m-%d').date()
    dt_value = datetime.combine(date_part, time_value)
    if hour_offset or minute_offset:
        from datetime import timedelta
        dt_value = dt_value + timedelta(hours=hour_offset, minutes=minute_offset)
    return dt_value.strftime('%Y-%m-%dT%H:%M:%S')


def local_booking_confirmation(user, flight_data):
    increment = PriceIncrement.objects.first()
    increment_value = Decimal(increment.increment_value if increment else 0)
    price = Decimal(str(flight_data['price']['total'])) * NAIRA_PER_USD + increment_value
    first_segment = flight_data['itineraries'][0]['segments'][0]

    confirmation = {
        'price': float(price),
        'created': datetime.now().strftime('%Y-%m-%d'),
        'reference': f'LOCAL-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'confirmed': 'CONFIRMED',
        'first_name': user.first_name or user.username,
        'last_name': user.last_name or '',
    }

    for index, itinerary in enumerate(flight_data['itineraries']):
        first = itinerary['segments'][0]
        confirmation[f'{index}firstFlightDepartureAirport'] = first['departure']['iataCode']
        confirmation[f'{index}firstFlightAirlineLogo'] = get_airline_logo(first['carrierCode'])
        confirmation[f'{index}firstFlightAirline'] = first['carrierCode']
        confirmation[f'{index}firstFlightDepartureDate'] = get_hour(first['departure']['at'])
        confirmation[f'{index}departureDate'] = first['departure']['at'].split('T', 1)[0]
        confirmation[f'{index}firstFlightArrivalAirport'] = first['arrival']['iataCode']
        confirmation[f'{index}firstFlightArrivalDate'] = get_hour(first['arrival']['at'])

        if len(itinerary['segments']) > 1:
            second = itinerary['segments'][1]
            confirmation[f'{index}secondFlightDepartureAirport'] = second['departure']['iataCode']
            confirmation[f'{index}secondFlightAirlineLogo'] = get_airline_logo(second['carrierCode'])
            confirmation[f'{index}secondFlightAirline'] = second['carrierCode']
            confirmation[f'{index}secondFlightDepartureDate'] = get_hour(second['departure']['at'])
            confirmation[f'{index}secondFlightArrivalAirport'] = second['arrival']['iataCode']
            confirmation[f'{index}secondFlightArrivalDate'] = get_hour(second['arrival']['at'])

    confirmation['origin'] = first_segment['departure']['iataCode']
    return confirmation


def get_airline_logo(carrier_code):
    return f'https://s1.apideeplink.com/images/airlines/{carrier_code}.png'


def get_hour(date_time):
    return datetime.strptime(date_time[0:19], '%Y-%m-%dT%H:%M:%S').strftime('%H:%M')
