import re
from datetime import datetime
from decimal import Decimal

from .local_flights import AIRPORT_LOOKUP, STATIC_AIRPORTS


LOCAL_HOTEL_RESULTS_TARGET = 12
LOCAL_HOTEL_ID_PREFIX = 'LOCAL-HOTEL-'
LOCAL_ROOM_MARKER = '-ROOM-'
LOCAL_HOTEL_SOURCES = {'LOCAL_HOTEL_DB', 'SYNTHETIC_HOTEL_DB'}

CITY_CODE_ALIASES = {
    'CDG': 'PAR',
    'ORY': 'PAR',
    'JFK': 'NYC',
    'EWR': 'NYC',
    'LGA': 'NYC',
    'LHR': 'LON',
    'LGW': 'LON',
    'NRT': 'TYO',
    'HND': 'TYO',
    'ORD': 'CHI',
    'YYZ': 'YTO',
}

NIGERIA_STATE_DESTINATIONS = [
    {'code': 'UMU', 'city': 'Umuahia', 'state': 'Abia', 'lat': 5.5249, 'lon': 7.4946, 'aliases': ('Aba',)},
    {'code': 'YOL', 'city': 'Yola', 'state': 'Adamawa', 'lat': 9.2035, 'lon': 12.4954, 'aliases': ()},
    {'code': 'QUO', 'city': 'Uyo', 'state': 'Akwa Ibom', 'lat': 5.0377, 'lon': 7.9128, 'aliases': ('Akwa-Ibom',)},
    {'code': 'AWK', 'city': 'Awka', 'state': 'Anambra', 'lat': 6.2101, 'lon': 7.0741, 'aliases': ('Onitsha', 'Nnewi')},
    {'code': 'BCU', 'city': 'Bauchi', 'state': 'Bauchi', 'lat': 10.3158, 'lon': 9.8442, 'aliases': ()},
    {'code': 'YEN', 'city': 'Yenagoa', 'state': 'Bayelsa', 'lat': 4.9267, 'lon': 6.2676, 'aliases': ()},
    {'code': 'MDI', 'city': 'Makurdi', 'state': 'Benue', 'lat': 7.7322, 'lon': 8.5391, 'aliases': ()},
    {'code': 'MIU', 'city': 'Maiduguri', 'state': 'Borno', 'lat': 11.8311, 'lon': 13.1510, 'aliases': ()},
    {'code': 'CBQ', 'city': 'Calabar', 'state': 'Cross River', 'lat': 4.9757, 'lon': 8.3417, 'aliases': ('Cross-River',)},
    {'code': 'ABB', 'city': 'Asaba', 'state': 'Delta', 'lat': 6.2050, 'lon': 6.6959, 'aliases': ('Warri', 'QRW')},
    {'code': 'EBK', 'city': 'Abakaliki', 'state': 'Ebonyi', 'lat': 6.3249, 'lon': 8.1137, 'aliases': ()},
    {'code': 'BNI', 'city': 'Benin City', 'state': 'Edo', 'lat': 6.3350, 'lon': 5.6037, 'aliases': ('Benin',)},
    {'code': 'ENU', 'city': 'Enugu', 'state': 'Enugu', 'lat': 6.4474, 'lon': 7.5139, 'aliases': ()},
    {'code': 'ABV', 'city': 'Abuja', 'state': 'FCT', 'lat': 9.0765, 'lon': 7.3986, 'aliases': ('Federal Capital Territory', 'Abuja FCT')},
    {'code': 'GMO', 'city': 'Gombe', 'state': 'Gombe', 'lat': 10.2897, 'lon': 11.1673, 'aliases': ()},
    {'code': 'QOW', 'city': 'Owerri', 'state': 'Imo', 'lat': 5.4763, 'lon': 7.0259, 'aliases': ()},
    {'code': 'DUT', 'city': 'Dutse', 'state': 'Jigawa', 'lat': 11.7562, 'lon': 9.3389, 'aliases': ()},
    {'code': 'KAD', 'city': 'Kaduna', 'state': 'Kaduna', 'lat': 10.5105, 'lon': 7.4165, 'aliases': ()},
    {'code': 'KAN', 'city': 'Kano', 'state': 'Kano', 'lat': 12.0022, 'lon': 8.5920, 'aliases': ()},
    {'code': 'DKA', 'city': 'Katsina', 'state': 'Katsina', 'lat': 12.9855, 'lon': 7.6171, 'aliases': ()},
    {'code': 'BIR', 'city': 'Birnin Kebbi', 'state': 'Kebbi', 'lat': 12.4539, 'lon': 4.1975, 'aliases': ()},
    {'code': 'LOK', 'city': 'Lokoja', 'state': 'Kogi', 'lat': 7.8023, 'lon': 6.7333, 'aliases': ()},
    {'code': 'ILR', 'city': 'Ilorin', 'state': 'Kwara', 'lat': 8.4966, 'lon': 4.5421, 'aliases': ()},
    {'code': 'LOS', 'city': 'Lagos', 'state': 'Lagos', 'lat': 6.5244, 'lon': 3.3792, 'aliases': ('Ikeja', 'Victoria Island', 'Lekki')},
    {'code': 'LAF', 'city': 'Lafia', 'state': 'Nasarawa', 'lat': 8.4961, 'lon': 8.5153, 'aliases': ()},
    {'code': 'MXJ', 'city': 'Minna', 'state': 'Niger', 'lat': 9.5836, 'lon': 6.5463, 'aliases': ()},
    {'code': 'ABE', 'city': 'Abeokuta', 'state': 'Ogun', 'lat': 7.1475, 'lon': 3.3619, 'aliases': ()},
    {'code': 'AKR', 'city': 'Akure', 'state': 'Ondo', 'lat': 7.2571, 'lon': 5.2058, 'aliases': ()},
    {'code': 'OSO', 'city': 'Osogbo', 'state': 'Osun', 'lat': 7.7827, 'lon': 4.5418, 'aliases': ('Oshogbo',)},
    {'code': 'IBA', 'city': 'Ibadan', 'state': 'Oyo', 'lat': 7.3775, 'lon': 3.9470, 'aliases': ()},
    {'code': 'JOS', 'city': 'Jos', 'state': 'Plateau', 'lat': 9.8965, 'lon': 8.8583, 'aliases': ()},
    {'code': 'PHC', 'city': 'Port Harcourt', 'state': 'Rivers', 'lat': 4.8156, 'lon': 7.0498, 'aliases': ('Port-Harcourt',)},
    {'code': 'SKO', 'city': 'Sokoto', 'state': 'Sokoto', 'lat': 13.0059, 'lon': 5.2476, 'aliases': ()},
    {'code': 'JAL', 'city': 'Jalingo', 'state': 'Taraba', 'lat': 8.8937, 'lon': 11.3596, 'aliases': ()},
    {'code': 'DAM', 'city': 'Damaturu', 'state': 'Yobe', 'lat': 11.7460, 'lon': 11.9608, 'aliases': ()},
    {'code': 'GUS', 'city': 'Gusau', 'state': 'Zamfara', 'lat': 12.1702, 'lon': 6.6641, 'aliases': ()},
]


def build_city_meta():
    cities = {}
    for airport in STATIC_AIRPORTS:
        code = CITY_CODE_ALIASES.get(airport['code'], airport['code'])
        aliases = {
            airport['code'],
            airport['name'],
            airport['city'],
            airport.get('state', ''),
            *airport.get('aliases', ()),
        }

        if code not in cities:
            cities[code] = {
                'city': airport['city'],
                'state': airport.get('state', ''),
                'country': airport['country'],
                'region': airport['region'],
                'lat': airport['lat'],
                'lon': airport['lon'],
                'aliases': aliases,
            }
        else:
            cities[code]['aliases'].update(aliases)

    for destination in NIGERIA_STATE_DESTINATIONS:
        code = destination['code']
        state = destination['state']
        aliases = {
            code,
            destination['city'],
            state,
            f'{state} State',
            f'{state} Nigeria',
            f'{state} State Nigeria',
            *destination.get('aliases', ()),
        }
        if code not in cities:
            cities[code] = {
                'city': destination['city'],
                'state': state,
                'country': 'Nigeria',
                'region': 'NG',
                'lat': destination['lat'],
                'lon': destination['lon'],
                'aliases': aliases,
            }
        else:
            cities[code].update({
                'city': destination['city'],
                'state': state,
                'country': 'Nigeria',
                'region': 'NG',
                'lat': destination['lat'],
                'lon': destination['lon'],
            })
            cities[code]['aliases'].update(aliases)

    overrides = {
        'PAR': {'city': 'Paris', 'country': 'France', 'aliases': {'CDG', 'Paris'}},
        'NYC': {'city': 'New York', 'country': 'United States', 'aliases': {'JFK', 'New York City', 'Manhattan'}},
        'LON': {'city': 'London', 'country': 'United Kingdom', 'aliases': {'LHR', 'Heathrow'}},
        'TYO': {'city': 'Tokyo', 'country': 'Japan', 'aliases': {'NRT', 'HND', 'Haneda', 'Narita'}},
        'CHI': {'city': 'Chicago', 'country': 'United States', 'aliases': {'ORD', 'O Hare'}},
        'YTO': {'city': 'Toronto', 'country': 'Canada', 'aliases': {'YYZ', 'Pearson'}},
    }
    for code, override in overrides.items():
        if code in cities:
            cities[code].update({
                key: value
                for key, value in override.items()
                if key != 'aliases'
            })
            cities[code]['aliases'].update(override.get('aliases', set()))

    for city in cities.values():
        city['aliases'] = tuple(sorted(filter(None, city['aliases'])))
    return cities


HOTEL_CITY_META = build_city_meta()

STATIC_HOTEL_PROFILES = {
    'LOS': [
        {
            'name': 'Lagos Marina Hotel',
            'district': 'Victoria Island',
            'address': 'Adetokunbo Ademola Street, Victoria Island, Lagos',
            'lat': 6.4281,
            'lon': 3.4219,
            'base_price': '185',
        },
        {
            'name': 'Ikeja Business Suites',
            'district': 'Ikeja GRA',
            'address': 'Isaac John Street, Ikeja GRA, Lagos',
            'lat': 6.5763,
            'lon': 3.3588,
            'base_price': '142',
        },
    ],
    'ABV': [
        {
            'name': 'Central Abuja Hotel',
            'district': 'Central Business District',
            'address': 'Ahmadu Bello Way, Central Business District, Abuja',
            'lat': 9.0579,
            'lon': 7.4951,
            'base_price': '168',
        },
        {
            'name': 'Wuse Executive Lodge',
            'district': 'Wuse 2',
            'address': 'Aminu Kano Crescent, Wuse 2, Abuja',
            'lat': 9.0813,
            'lon': 7.4749,
            'base_price': '136',
        },
    ],
    'PHC': [
        {
            'name': 'Port Harcourt Garden Suites',
            'district': 'GRA Phase 2',
            'address': 'Aba Road, GRA Phase 2, Port Harcourt',
            'lat': 4.8242,
            'lon': 7.0336,
            'base_price': '128',
        },
    ],
    'ACC': [
        {
            'name': 'Accra Airport Hotel',
            'district': 'Airport City',
            'address': 'Airport Avenue, Airport City, Accra',
            'lat': 5.6037,
            'lon': -0.1869,
            'base_price': '176',
        },
    ],
    'DXB': [
        {
            'name': 'Dubai Creek Grand Hotel',
            'district': 'Deira',
            'address': 'Baniyas Road, Deira, Dubai',
            'lat': 25.2644,
            'lon': 55.3117,
            'base_price': '235',
        },
    ],
    'PAR': [
        {
            'name': 'Paris Opera Suites',
            'district': 'Opera',
            'address': 'Rue La Fayette, 9th Arrondissement, Paris',
            'lat': 48.8755,
            'lon': 2.3316,
            'base_price': '248',
        },
    ],
    'LON': [
        {
            'name': 'London Kensington Hotel',
            'district': 'Kensington',
            'address': 'Cromwell Road, Kensington, London',
            'lat': 51.4945,
            'lon': -0.1910,
            'base_price': '226',
        },
    ],
    'NYC': [
        {
            'name': 'Midtown Manhattan Suites',
            'district': 'Midtown',
            'address': 'West 45th Street, Midtown Manhattan, New York',
            'lat': 40.7581,
            'lon': -73.9855,
            'base_price': '268',
        },
    ],
    'TYO': [
        {
            'name': 'Tokyo Ginza Hotel',
            'district': 'Ginza',
            'address': 'Ginza Chuo City, Tokyo',
            'lat': 35.6710,
            'lon': 139.7650,
            'base_price': '214',
        },
    ],
    'NBO': [
        {
            'name': 'Nairobi Westlands Hotel',
            'district': 'Westlands',
            'address': 'Waiyaki Way, Westlands, Nairobi',
            'lat': -1.2674,
            'lon': 36.8065,
            'base_price': '154',
        },
    ],
}

HOTEL_NAME_VARIANTS = [
    'Grand {city} Hotel',
    '{city} Central Suites',
    '{city} City Lodge',
    'The {city} Residence',
    '{city} Business Hotel',
    '{city} Airport Inn',
    '{city} Garden Suites',
    '{city} Premier Hotel',
    '{city} Harbor Hotel',
    '{city} Executive Rooms',
]

DISTRICT_VARIANTS = [
    'City Center',
    'Business District',
    'Airport Road',
    'Central Avenue',
    'Old Town',
    'Riverside',
]

ROOM_VARIANTS = [
    {
        'type': 'STANDARD',
        'name': 'Standard Room',
        'description': 'Standard room with queen bed, workspace, WiFi, and breakfast access.',
        'multiplier': Decimal('1.00'),
    },
    {
        'type': 'DELUXE',
        'name': 'Deluxe Room',
        'description': 'Deluxe room with king bed, city view, WiFi, and daily breakfast.',
        'multiplier': Decimal('1.28'),
    },
    {
        'type': 'SUITE',
        'name': 'Executive Suite',
        'description': 'Executive suite with separate lounge, premium amenities, and breakfast.',
        'multiplier': Decimal('1.68'),
    },
]


def normalize_city_code(value):
    text = (value or '').strip()
    if not text:
        return ''

    leading = text.split(',', 1)[0].strip().upper()
    if leading in HOTEL_CITY_META:
        return leading
    if leading in CITY_CODE_ALIASES:
        return CITY_CODE_ALIASES[leading]

    search_values = hotel_search_variants(text)
    for code, meta in HOTEL_CITY_META.items():
        terms = hotel_city_search_terms(code, meta)
        if search_values & terms:
            return code

    for code, meta in HOTEL_CITY_META.items():
        terms = hotel_city_partial_terms(code, meta)
        for search_value in search_values:
            if len(search_value) >= 4 and any(search_value in term or term in search_value for term in terms):
                return code

    if len(leading) >= 3 and leading[:3].isalpha():
        return CITY_CODE_ALIASES.get(leading[:3], leading[:3])
    return leading


def local_hotel_search(city_code, checkin_date, checkout_date, guest_count=1, max_results=LOCAL_HOTEL_RESULTS_TARGET):
    city_code = normalize_city_code(city_code)
    guest_count = normalize_guest_count(guest_count)
    max_results = max(int(max_results or LOCAL_HOTEL_RESULTS_TARGET), 1)

    hotels = []
    for index in range(1, max_results + 1):
        profile, source = hotel_profile_for_index(city_code, index)
        hotels.append(
            build_hotel_data(
                profile,
                city_code,
                index,
                checkin_date,
                checkout_date,
                guest_count,
                source,
                include_all_rooms=False,
            )
        )
    return hotels


def local_room_search(hotel_id, checkin_date, checkout_date, guest_count=1):
    city_code, index = parse_local_hotel_id(hotel_id)
    profile, source = hotel_profile_for_index(city_code, index)
    return [
        build_hotel_data(
            profile,
            city_code,
            index,
            checkin_date,
            checkout_date,
            normalize_guest_count(guest_count),
            source,
            include_all_rooms=True,
        )
    ]


def local_hotel_offer(offer_id):
    hotel_id, room_index, checkin_date, checkout_date, guest_count = parse_local_offer_id(offer_id)
    rooms = local_room_search(hotel_id, checkin_date, checkout_date, guest_count)
    selected_offer_id = make_room_offer_id(hotel_id, room_index, checkin_date, checkout_date, guest_count)
    selected_offer = next(
        (offer for offer in rooms[0]['offers'] if offer['id'] == selected_offer_id),
        rooms[0]['offers'][0],
    )
    rooms[0]['offers'] = [selected_offer]
    return rooms[0]


def local_hotel_booking_confirmation(user, offer_id):
    user_id = getattr(user, 'id', None) or 'guest'
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return [
        {
            'id': f'LOCAL-HOTEL-{timestamp}-{user_id}',
            'providerConfirmationId': f'LOCAL-{timestamp[-6:]}-{abs(hash(offer_id)) % 100000:05d}',
        }
    ]


def local_hotel_city_search(term=''):
    needles = hotel_search_variants(term)
    results = []
    for code in sorted(HOTEL_CITY_META):
        meta = HOTEL_CITY_META[code]
        terms = hotel_city_search_terms(code, meta)
        partial_terms = hotel_city_partial_terms(code, meta)
        if not needles or needles & terms or any(
            len(needle) >= 2 and any(needle in term_value for term_value in partial_terms)
            for needle in needles
        ):
            results.append(hotel_city_label(code, meta))
    return results


def is_local_hotel_id(hotel_id):
    return str(hotel_id or '').startswith(LOCAL_HOTEL_ID_PREFIX)


def is_local_hotel_offer_id(offer_id):
    value = str(offer_id or '')
    return LOCAL_ROOM_MARKER in value and is_local_hotel_id(value.split(LOCAL_ROOM_MARKER, 1)[0])


def hotel_city_label(code, meta=None):
    meta = meta or get_city_meta(code)
    location_parts = [meta['city']]
    if meta.get('state') and meta['state'] != meta['city']:
        location_parts.append(meta['state'])
    location_parts.append(meta['country'])
    return f"{code}, {', '.join(location_parts)}"


def hotel_city_search_text(code, meta):
    return ' '.join(sorted(hotel_city_search_terms(code, meta)))


def hotel_city_search_terms(code, meta):
    parts = [
        code,
        meta.get('city', ''),
        meta.get('state', ''),
        meta.get('country', ''),
        *meta.get('aliases', ()),
    ]
    if meta.get('country') == 'Nigeria' and meta.get('state'):
        parts.extend([
            f"{meta['state']} State",
            f"{meta['state']} Nigeria",
            f"{meta['state']} State Nigeria",
            f"{meta['city']} {meta['state']}",
            f"{meta['city']} {meta['state']} Nigeria",
        ])
    return {
        normalize_search_phrase(part)
        for part in parts
        if normalize_search_phrase(part)
    }


def hotel_city_partial_terms(code, meta):
    country = normalize_search_phrase(meta.get('country', ''))
    return {
        term
        for term in hotel_city_search_terms(code, meta)
        if not country or country not in term
    }


def hotel_search_variants(value):
    normalized = normalize_search_phrase(value)
    if not normalized:
        return set()

    variants = {normalized}
    replacements = {
        normalized.replace(' STATE NIGERIA', ''),
        normalized.replace(' STATE', ''),
        normalized.replace(' NIGERIA', ''),
        normalized.replace(' FEDERAL CAPITAL TERRITORY', ' FCT'),
    }
    if normalized.startswith('STATE OF '):
        replacements.add(normalized.replace('STATE OF ', '', 1))
    variants.update(filter(None, replacements))
    return variants


def normalize_search_phrase(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9]+', ' ', str(value or '').upper())).strip()


def hotel_profile_for_index(city_code, index):
    city_code = normalize_city_code(city_code)
    profiles = STATIC_HOTEL_PROFILES.get(city_code, [])
    if index <= len(profiles):
        return profiles[index - 1], 'LOCAL_HOTEL_DB'
    return build_synthetic_profile(city_code, index), 'SYNTHETIC_HOTEL_DB'


def build_synthetic_profile(city_code, index):
    city_meta = get_city_meta(city_code)
    city = city_meta['city'].title()
    variant = HOTEL_NAME_VARIANTS[(index - 1) % len(HOTEL_NAME_VARIANTS)]
    district = DISTRICT_VARIANTS[(index - 1) % len(DISTRICT_VARIANTS)]
    offset = Decimal(index % 7) * Decimal('0.006')
    return {
        'name': variant.format(city=city),
        'district': district,
        'address': f'{district}, {city_meta["city"]}, {city_meta["country"]}',
        'lat': float(Decimal(str(city_meta['lat'])) + offset),
        'lon': float(Decimal(str(city_meta['lon'])) - offset),
        'base_price': str(estimate_base_price(city_code, index)),
    }


def build_hotel_data(profile, city_code, hotel_index, checkin_date, checkout_date, guest_count, source, include_all_rooms=False):
    hotel_id = make_hotel_id(city_code, hotel_index)
    room_offers = build_room_offers(profile, hotel_id, checkin_date, checkout_date, guest_count)
    return {
        'type': 'hotel-offers',
        'source': source,
        'hotel': {
            'type': 'hotel',
            'hotelId': hotel_id,
            'chainCode': 'OB',
            'name': profile['name'],
            'cityCode': city_code,
            'latitude': profile['lat'],
            'longitude': profile['lon'],
            'address': profile['address'],
        },
        'available': True,
        'offers': room_offers if include_all_rooms else [room_offers[0]],
    }


def build_room_offers(profile, hotel_id, checkin_date, checkout_date, guest_count):
    nights = nights_between(checkin_date, checkout_date)
    guest_factor = Decimal('1.00') + (Decimal(max(guest_count - 1, 0)) * Decimal('0.25'))
    base_price = Decimal(str(profile['base_price']))
    offers = []

    for index, variant in enumerate(ROOM_VARIANTS, start=1):
        total = (base_price * variant['multiplier'] * Decimal(nights) * guest_factor).quantize(Decimal('0.01'))
        offers.append(
            {
                'id': make_room_offer_id(hotel_id, index, checkin_date, checkout_date, guest_count),
                'checkInDate': checkin_date,
                'checkOutDate': checkout_date,
                'room': {
                    'type': variant['type'],
                    'description': {
                        'text': f"{variant['name']} at {profile['name']}. {variant['description']}",
                    },
                },
                'guests': {
                    'adults': guest_count,
                },
                'price': {
                    'currency': 'USD',
                    'total': f'{total:.2f}',
                },
            }
        )
    return offers


def make_hotel_id(city_code, index):
    return f'{LOCAL_HOTEL_ID_PREFIX}{normalize_city_code(city_code)}-{int(index)}'


def make_room_offer_id(hotel_id, room_index, checkin_date, checkout_date, guest_count):
    return (
        f'{hotel_id}{LOCAL_ROOM_MARKER}{int(room_index)}-'
        f'{compact_date(checkin_date)}-{compact_date(checkout_date)}-G{normalize_guest_count(guest_count)}'
    )


def parse_local_hotel_id(hotel_id):
    value = str(hotel_id or '')
    if not is_local_hotel_id(value):
        raise ValueError(f'Unsupported local hotel id: {hotel_id}')
    city_and_index = value[len(LOCAL_HOTEL_ID_PREFIX):]
    city_code, index = city_and_index.rsplit('-', 1)
    return normalize_city_code(city_code), int(index)


def parse_local_offer_id(offer_id):
    value = str(offer_id or '')
    if not is_local_hotel_offer_id(value):
        raise ValueError(f'Unsupported local hotel offer id: {offer_id}')

    hotel_id, room_part = value.split(LOCAL_ROOM_MARKER, 1)
    room_index, checkin_date, checkout_date, guests = room_part.split('-', 3)
    return (
        hotel_id,
        int(room_index),
        expand_compact_date(checkin_date),
        expand_compact_date(checkout_date),
        normalize_guest_count(guests.lstrip('G')),
    )


def normalize_guest_count(value):
    try:
        return max(int(value or 1), 1)
    except (TypeError, ValueError):
        return 1


def compact_date(date_value):
    return str(date_value or '').replace('-', '')


def expand_compact_date(date_value):
    value = str(date_value or '')
    if len(value) == 8 and value.isdigit():
        return f'{value[0:4]}-{value[4:6]}-{value[6:8]}'
    return value


def nights_between(checkin_date, checkout_date):
    try:
        checkin = datetime.strptime(checkin_date, '%Y-%m-%d').date()
        checkout = datetime.strptime(checkout_date, '%Y-%m-%d').date()
        return max((checkout - checkin).days, 1)
    except (TypeError, ValueError):
        return 1


def get_city_meta(city_code):
    city_code = normalize_city_code(city_code)
    if city_code in HOTEL_CITY_META:
        return HOTEL_CITY_META[city_code]

    airport = AIRPORT_LOOKUP.get(city_code)
    if airport:
        return {
            'city': airport['city'],
            'state': airport.get('state', ''),
            'country': airport['country'],
            'region': airport['region'],
            'lat': airport['lat'],
            'lon': airport['lon'],
            'aliases': (airport['code'], airport['name']),
        }

    return {
        'city': city_code or 'Destination',
        'state': '',
        'country': 'Worldwide',
        'region': 'UNKNOWN',
        'lat': 6.5244,
        'lon': 3.3792,
        'aliases': (),
    }


def estimate_base_price(city_code, index):
    region = get_city_meta(city_code).get('region', 'UNKNOWN')
    base = {
        'NG': Decimal('118'),
        'WEST_AFRICA': Decimal('132'),
        'AFRICA': Decimal('145'),
        'MIDDLE_EAST': Decimal('205'),
        'EUROPE': Decimal('218'),
        'NORTH_AMERICA': Decimal('238'),
        'ASIA': Decimal('186'),
        'UNKNOWN': Decimal('130'),
    }.get(region, Decimal('130'))
    return base + (Decimal(index % 6) * Decimal('14'))
