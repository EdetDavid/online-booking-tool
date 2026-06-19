from .hotel import format_price_naira


class Room:
    def __init__(self, rooms):
        self.rooms = rooms

    def construct_room(self):
        hotel_rooms = []
        try:
            for room in self.rooms[0]['offers']:
                offer = {}
                price = room['price']
                offer['price'] = format_price_naira(
                    price.get('total'),
                    price.get('currency', 'USD'),
                )
                room_info = room.get('room', {})
                description = room_info.get('description', {}).get('text')
                offer['description'] = description or room_info.get('type', 'Hotel room')
                offer['roomType'] = (
                    room_info.get('description', {}).get('text', '').split('.', 1)[0]
                    or room_info.get('type', 'Hotel room')
                )
                offer['offerID'] = room['id']
                offer['checkInDate'] = room.get('checkInDate', '')
                offer['checkOutDate'] = room.get('checkOutDate', '')
                offer['guests'] = room.get('guests', {}).get('adults', 1)
                hotel_rooms.append(offer)
        except (TypeError, AttributeError, KeyError, IndexError):
            pass
        return hotel_rooms
