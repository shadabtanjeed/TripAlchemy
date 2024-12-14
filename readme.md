# TripAlchemy 🌍✈️  

**TripAlchemy** is an AI-powered travel planning platform that simplifies trip management from planning to automated vlog creation.  

## Status  
**Project Phase**: Under Active Development 🚧  

## Tech Stack  
- **Backend**: Django  
- **Frontend**: HTML, Bootstrap, CSS  
- **Database**: Firebase  
- **APIs**:  
  - [Google Maps](https://developers.google.com/maps)  
  - [Open-Meteo](https://open-meteo.com/en/docs)  
  - [Booking.com](https://rapidapi.com/ntd119/api/booking-com18)  
  - [Currency Conversion](https://rapidapi.com/principalapis/api/currency-conversion-and-exchange-rates)  
- **AI Tools**: [Google Gemini 1.5](https://ai.google.dev/gemini-api/docs)  

## Features  
- **Intelligent Itinerary Generation**: Destination-based planning with recommendations for transportation, accommodation, and budget.  
- **Interactive Map Integration**: Comprehensive route visualization with dynamic markers highlighting tourist attractions, accommodations, restaurants, and points of interest.  
- **Weather Notification System**: Location-based updates and severe weather alerts.  
- **Memory Preservation**: Automated trip blog creation and image search functionality.  
- **Travel Vlog Creation**: AI-powered video generation with mood-based music integration.  

## Screenshots  

### Login Page  
![Login](https://github.com/user-attachments/assets/4bed4f9c-aa9d-40d7-9110-26413d724f34)  

### Trip Details Page  
![Trip Details](https://github.com/user-attachments/assets/5f8c39de-b04f-426d-b08e-abb5c862168d)  

### Flight Booking Page  
![Flight Page](https://github.com/user-attachments/assets/beb47f1e-419c-41b0-a120-2a90ec021411)  

### Hotel Booking Page  
![Hotel Page](https://github.com/user-attachments/assets/51faebb4-9d6f-49bf-8d03-42025dae317f)  

### Itinerary Page (Part 1)  
![Itinerary Page 1](https://github.com/user-attachments/assets/9d26acbb-204e-40bd-a81e-1a60df80a84c)  

### Itinerary Page (Part 2)  
![Itinerary Page 2](https://github.com/user-attachments/assets/55a533df-bcd9-43f0-b2f5-983851daa80e)  

### Weather Information Page  
![Weather Page](https://github.com/user-attachments/assets/5cc879b5-4a0d-48d9-b49f-3efd11d1b100)  

### Trip Summary Page  
![Trip Summary Page](https://github.com/user-attachments/assets/27bb309c-80f8-425c-a553-5329b9c8fcf3)  

*More screenshots will be added in future iterations.*  

## Getting Started  

### Prerequisites  
- Python 3.8+  
- Django  
- Firebase Account  
- API Keys (Google Maps, Google Gemini, Open-Meteo, Rapid-API)  

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/shadabtanjeed/Django-Firebase-User-Authentication-Boilerplate
   cd Django-Firebase-User-Authentication-Boilerplate
   ```

   Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Firebase Setup
    * Go to Firebase Console
    * Create a new project
    * Enable Authentication
    * Add web app to get configuration
    * Download service account key
    * Enable email/password based authentication

4. Environment Configuration
    * Create a `.env` file with the following variables:
        ```bash
        FIREBASE_API_KEY=your_api_key
        FIREBASE_AUTH_DOMAIN=your_auth_domain
        FIREBASE_PROJECT_ID=your_project_id
        FIREBASE_STORAGE_BUCKET=your_storage_bucket
        FIREBASE_MESSAGING_SENDER_ID=your_messaging_sender_id
        FIREBASE_APP_ID=your_app_id
        GEMINI_API_KEY=YOUR_GEMINI_KEY
        RAPID_API_BOOKING_KEY = YOUR_API_KEY
        GOOGLE_MAP_API_KEY = YOUR_API_KEY
        ```

        For RAPID-API key, subscribe to any of the APIs hosted on the platform and acquire the key from example header.

5. Add `serviceAccountKey.json` file
    * Download the service key json file from firebase:
         * Go to project settings -> Service Accounts -> Generate Private Key
    * Rename it as `serviceAccountKey.json`.
    * Put it in the directory: `django_project`

6. Run the server
   ```bash
   python manage.py runserver
   ```
## Limitations  
- Due to Firebase's limitations with Python integration, signup is handled by the backend in the `signup_view` function, whereas login is managed on the client side in the `login_view` function.  
- Since the authentication system uses email identifiers, "@email.com" is appended to usernames when interacting with Firebase.  
- Currently, only major cities are supported.  
- Only flights are available as a mode of transportation due to a lack of data on buses or trains.  
- Flights with stops do not yet have clear indications on the flight picker page. However, this can be inferred from flight details.  
- Retrieving the hotel list requires performing three sequential API calls, resulting in significant load times. The same applies to itinerary generation due to the large prompt size.  

## Future Iterations  
- **Gallery Option**: Add a gallery for completed trips.  
- **Image Search**: Enable natural language-based search for uploaded images.  
- **Vlog Generation**: Create vlogs from uploaded images with automatic mood-based background music.  
