# Course Discovery API

A FastAPI backend for course aggregation, search, categories, user profiles, favorites, and notifications.

## Project Structure

```
app/
├── main.py                 # FastAPI application entry point
├── core/                   # Core configuration and security
│   ├── config.py          # Environment configuration
│   └── security.py        # Authentication and authorization
├── models/                 # Pydantic data models
│   ├── user.py            # User models
│   ├── course.py          # Course models
│   ├── category.py        # Category models
│   └── notification.py    # Notification models
├── routers/                # API route handlers
│   ├── auth.py            # Authentication endpoints
│   ├── users.py           # User profile and favorites
│   ├── courses.py         # Course search and details
│   ├── categories.py      # Category browsing
│   ├── admin_users.py     # Admin user management
│   └── admin_categories.py # Admin category management
├── services/               # Background services
│   ├── data_ingestion.py  # Course data scraping pipeline
│   ├── sentiment.py       # Sentiment analysis
│   ├── notification_service.py # User notifications
│   └── scheduler.py       # Background job scheduler
├── utils/                  # Utility modules
│   ├── keyword_queue.py   # Search keyword management
│   ├── category_tagger.py # Automatic course categorization
│   └── unify_data.py      # Data unification
└── requirements.txt        # Python dependencies
```

## Features

- **JWT Authentication**: User registration and login with JWT tokens
- **Course Search & Detail**: Full-text search with ranking algorithm
- **Category Management**: Automatic course categorization and browsing
- **User Profiles**: Favorites and notifications
- **Admin Dashboard**: User and category management
- **Background Services**: Automated course scraping and sentiment analysis

## Quick Start

### 1. Environment Setup

Create a `.env` file in the root directory:

```bash
# Copy the example configuration
cp env.example .env
```

Edit `.env` with your actual values:

```env
# MongoDB connection
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/course_app?retryWrites=true&w=majority

# JWT secret (use a strong random value)
SECRET_KEY=your-super-secret-jwt-key-change-this

# Optional parameters
ACCESS_TOKEN_EXPIRE_HOURS=4
ALPHA=0.7
BETA=0.2
TAG_THRESHOLD=0.2
PSEUDOCOUNT=10
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Application

```bash
# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Access the API

- **API Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Authentication
- `POST /users/register` - Register new user
- `POST /users/login` - User login

### User Profile
- `GET /users/me` - Get current user profile
- `PUT /users/me` - Update user profile
- `POST /users/me/favorites` - Add course to favorites
- `DELETE /users/me/favorites/{course_id}` - Remove from favorites
- `GET /users/me/notifications` - Get user notifications

### Courses
- `GET /search` - Search courses with ranking
- `GET /course/{course_id}` - Get course details

### Categories
- `GET /categories` - List all categories
- `GET /categories/{name}/courses` - Get courses by category

### Admin (requires admin privileges)
- `GET /admin/users` - List all users
- `PUT /admin/users/{id}/block` - Block/unblock user
- `DELETE /admin/users/{id}` - Delete user
- `POST /admin/categories` - Create category
- `GET /admin/categories/{id}` - Get category
- `PUT /admin/categories/{id}` - Update category
- `DELETE /admin/categories/{id}` - Delete category

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGO_URI` | MongoDB connection string | Required |
| `SECRET_KEY` | JWT signing secret | Required |
| `ACCESS_TOKEN_EXPIRE_HOURS` | JWT token lifetime | 4 |
| `ALPHA` | Text relevance weight in search | 0.7 |
| `BETA` | Popularity weight in search | 0.2 |
| `TAG_THRESHOLD` | Category tagging threshold | 0.2 |
| `PSEUDOCOUNT` | Bayesian smoothing parameter | 10 |

### Database Collections

The application uses the following MongoDB collections:

- `users` - User accounts and profiles
- `courses` - Course data with reviews and categories
- `categories` - Course categories with keywords
- `keyword_queue` - Search keywords for scraping
- `search_requests` - User search requests for notifications

## Development

### Running with Auto-reload

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Code Style

Run linter to check code quality:

```bash
flake8 .
```

### Type Checking

```bash
mypy .
```

## Background Services

The application includes background services for data processing:

### Scheduler Service

```bash
python services/scheduler.py
```

This runs:
- Course data ingestion (every 4 hours)
- Notification dispatch (every 4 hours)
- Sentiment analysis (daily at 2 AM)

## Common Issues & Solutions

### 1. Import Errors
**Error**: `ModuleNotFoundError: No module named 'routers'`
**Solution**: Ensure you're running from the correct directory with `__init__.py` files

### 2. MongoDB Connection
**Error**: `pymongo.errors.ServerSelectionTimeoutError`
**Solution**: Check your `MONGO_URI` in `.env` and network connectivity

### 3. JWT Errors
**Error**: `jose.exceptions.JWTError`
**Solution**: Verify your `SECRET_KEY` is set and consistent

### 4. Missing Dependencies
**Error**: `ModuleNotFoundError: No module named 'textblob'`
**Solution**: Run `pip install -r requirements.txt`

### 5. Router Not Found
**Error**: `router` variable not defined
**Solution**: Ensure all router files have `router = APIRouter(...)` at the top

## Architecture

### Request Flow

1. **Authentication**: JWT tokens validate user identity
2. **Routing**: FastAPI routes requests to appropriate handlers
3. **Business Logic**: Services process the request
4. **Database**: MongoDB stores and retrieves data
5. **Response**: Pydantic models ensure consistent JSON output

### Background Processing

1. **Scheduler**: APScheduler manages periodic tasks
2. **Ingestion**: Scrapes and unifies course data
3. **Categorization**: Auto-tags courses with categories
4. **Sentiment**: Analyzes review sentiment
5. **Notifications**: Alerts users about new courses

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linters
5. Submit a pull request

## License

This project is licensed under the MIT License. 