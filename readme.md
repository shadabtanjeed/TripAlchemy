# TripAlchemy 🌍✈️

TripAlchemy is an AI-powered travel planning platform that simplifies trip management from planning to automated vlog creation. 

## Status
**Project Phase**: Under Active Development 🚧

## Tech Stack
- **Backend**: Django
- **Frontend**: HTML, Bootstrap, CSS
- **Database**: Firebase
- **APIs**: Google Maps, Open-Meteo, Booking.com
- **AI Tools**: Google Gemini 1.5 

## Features
- **Intelligent Itinerary Generation**: Destination-based planning with transport, accommodation, and budget recommendations
- **Interactive Map Integration**: Comprehensive route visualization with dynamic markers highlighting tourist attractions, accommodations, restaurants, and points of interest
- **Weather Notification System**: Location-based updates and severe weather alerts
- **Memory Preservation**: Automated trip blog and image search
- **Travel Vlog Creation**: AI-powered video generation with mood-based music

## Screenshots
*Screenshots will be added in future updates*

## Getting Started

### Prerequisites
- Python 3.8+
- Django
- Firebase Account
- API Keys (Mapbox, OpenWeather)

### Installation
```bash
git clone https://github.com/shadabtanjeed/TripAlchemy.git
cd TripAlchemy
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
## Limitations
- Only major cities are available currently.
- Only flights are available as mode of transportation due to lack of data  regarding bus or trains.
- Flights with stops do not have any indications in the flight picker page(yet). However, it can be easily known from the details of that flight.
- Getting hotel list relies on performing 3 API calls sequentially, reulting in HUUUUGE load time. Same case for itinerary generation.