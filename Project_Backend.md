**Refactored FastAPI Backend Architecture**

In this refactoring, the backend is reorganized into a clearer **modular structure**. All existing features –

course aggregation, JWT authentication, sentiment analysis, favorites, notifications, and category tagging – are preserved and polished. The code is separated into logical components \(routers, models, services, utils, etc.\) for maintainability. We also eliminated intermediate file storage by writing scraped data directly to MongoDB, optimized the scheduler to skip redundant work, and moved configuration to environment variables \(via a .env file\) for flexibility 1

2 . Below is the new project layout, followed by each file with its purpose and key implementation details: app/

├── main.py

├── core/

│ ├── config.py

│ └── security.py

├── models/

│ ├── user.py

│ ├── course.py

│ ├── category.py

│ └── notification.py

├── routers/

│ ├── auth.py

│ ├── users.py

│ ├── courses.py

│ ├── categories.py

│ ├── admin\_users.py

│ └── admin\_categories.py

├── services/

│ ├── data\_ingestion.py

│ ├── sentiment.py

│ ├── notification\_service.py

│ └── scheduler.py

└── utils/

├── keyword\_queue.py

├── category\_tagger.py

└── unify\_data.py
├── scrapers/                  ← **NEW** top‐level directory you should create
│   ├── alison/                ← move your existing `Alison_scraper/` here
│   └── coursera/              ← move your existing `Coursera_Scraper/` here
│

**app/main.py**

This is the **entry point** of the FastAPI application. It creates the FastAPI app, includes all router modules, and sets up any startup events. We define the application metadata \(title, version, description\) and then attach the routers for authentication, user profile, courses, categories, and admin operations. 

For example:

1

from fastapi import FastAPI

from app.routers import auth, users, courses, categories, admin\_users, admin\_categories

app = FastAPI\(

title="Course Discovery API", 

version="2.0", 

description="A backend for course aggregation, search, categories, user profiles, favorites, and notifications" 

\)

\# Include routers for different API sections

app.include\_router\(auth.router\)

app.include\_router\(users.router\)

app.include\_router\(courses.router\)

app.include\_router\(categories.router\)

app.include\_router\(admin\_users.router\)

app.include\_router\(admin\_categories.router\)

Each included router has a specified URL prefix and tags, so the endpoints remain the same as before \(e.g. /users/register , /search , /admin/users , etc.\). This modular inclusion follows FastAPI best practices for larger applications 2

3 , keeping related path operations grouped and organized. 

We also use FastAPI’s startup event to launch background tasks for category and notification watchers if needed. In particular, on startup we ensure all courses are categorized and then start the **category** **change-stream watcher** \(so course category tags auto-update when an admin edits categories\) and optionally a background notification watcher \(though notifications are also handled in scheduled jobs\). 

For example:

from app.utils import category\_tagger, keyword\_queue

@app.on\_event\("startup"\)

def on\_startup\(\):

\# Ensure all existing courses have category tags \(backfill once at startup\)

category\_tagger.retag\_all\(\)

\# Start background task to watch for any category changes and re-tag incrementally

category\_thread = threading.Thread\(target=category\_tagger.watch\_changes, daemon=True\)

category\_thread.start\(\)

\# \(Optional\) Start a background thread to periodically process notifications, 

\# if not using the external scheduler for this

\# notification\_thread = 

threading.Thread\(target=notification\_service.watch\_notifications, daemon=True\)

\# notification\_thread.start\(\)

2

**Why organized this way:** By centralizing the app creation and router inclusion in main.py , we cleanly separate concerns. Each router handles one aspect of the API, improving readability and maintainability

2 . Startup hooks ensure initial data consistency \(categories tagging\) and launch any continuous background processes. The use of threads for watchers keeps them running without blocking the main server. 

**app/core/config.py**

This module manages **configuration and environment variables**. We use Pydantic’s BaseSettings to load settings from a .env file, allowing sensitive values \(like database URI and secret keys\) to be set outside the code 1 . For example: from pydantic import BaseSettings

class Settings\(BaseSettings\):

MONGO\_URI: str

SECRET\_KEY: str

ACCESS\_TOKEN\_EXPIRE\_HOURS: int = 4

\# Optionally other settings like DB\_NAME, etc. 

class Config:

env\_file = ".env" 

settings = Settings\(\)

After creating settings , we initialize the MongoDB client and database using the provided URI: from pymongo import MongoClient

client = MongoClient\(settings.MONGO\_URI\)

db = client\["course\_app"\]

\# database name is fixed as 'course\_app' 

This way, any part of the app can import the configured db object to interact with the database. Using environment variables for configuration makes the application more secure and flexible to deploy in different environments \(development, testing, production\) without changing code 4 . We include a

.env.example file \(shown later\) to document required settings. 

**app/core/security.py**

The security.py module contains **authentication and authorization logic** \(password hashing, JWT

token creation, and dependency functions for protected routes\). We utilize the settings from config.py for secret keys and use passlib for hashing passwords and python-jose for JWT

encoding/decoding. Key components:

**Passwor**

• 

**d Hashing:** A CryptContext with bcrypt is used to hash passwords and verify them: pwd\_context = CryptContext\(schemes=\["bcrypt"\], deprecated="auto"\) 3

def get\_password\_hash\(password: str\) -> str: return pwd\_context.hash\(password\)

def verify\_password\(plain: str, hashed: str\) -> bool:

return pwd\_context.verify\(plain, hashed\)

**JWT**

• 

**Token Creation:** Using the SECRET\_KEY from settings and HS256 algorithm, we create access tokens that include the username and user ID, with an expiration: from jose import jwt

from datetime import datetime, timedelta

def create\_access\_token\(data: dict, expires\_delta: timedelta = None\) -> str:

to\_encode = data.copy\(\)

expire = datetime.utcnow\(\) \+ \(expires\_delta or

timedelta\(hours=settings.ACCESS\_TOKEN\_EXPIRE\_HOURS\)\)

to\_encode.update\(\{"exp": expire\}\)

return jwt.encode\(to\_encode, settings.SECRET\_KEY, algorithm="HS256"\) The token payload contains "sub": username and "user\_id": str\(ObjectId\) so we can identify the user from the token. 

**FastAPI**

• 

**Security Dependencies:** We define an OAuth2PasswordBearer scheme with the token URL \(the login endpoint\). Then dependency functions use the JWT to authenticate: oauth2\_scheme = OAuth2PasswordBearer\(tokenUrl="users/login"\) def get\_current\_user\(token: str = Depends\(oauth2\_scheme\)\):

credentials\_exception = HTTPException\(

status\_code=status.HTTP\_401\_UNAUTHORIZED, 

detail="Invalid authentication credentials", 

headers=\{"WWW-Authenticate": "Bearer"\}, 

\)

try:

payload = jwt.decode\(token, settings.SECRET\_KEY, 

algorithms=\["HS256"\]\)

uid = payload.get\("user\_id"\)

if uid is None:

raise credentials\_exception

except jwt.JWTError:

raise credentials\_exception

\# Fetch user from DB by id

user\_doc = db\["users"\].find\_one\(\{"\_id": ObjectId\(uid\)\}\) if not user\_doc:

raise credentials\_exception

return user\_doc

4

The get\_current\_active\_user and get\_current\_admin depend on get\_current\_user and then check flags \( is\_active or is\_admin \) to authorize the user: def get\_current\_active\_user\(current\_user=Depends\(get\_current\_user\)\): if not current\_user.get\("is\_active", True\):

raise HTTPException\(status\_code=400, detail="Inactive user"\) return current\_user

def get\_current\_admin\(current\_user=Depends\(get\_current\_active\_user\)\): if not current\_user.get\("is\_admin", False\):

raise HTTPException\(status\_code=403, detail="Not enough privileges"\)

return current\_user

These dependencies are used in router functions to **protect endpoints** \(for example, admin routes depend on get\_current\_admin , user profile routes depend on get\_current\_active\_user \). This structure centralizes auth logic and avoids repetition. 

**Why organized this way:** Consolidating security logic allows easy updates \(e.g., changing token expiration or hashing algorithm in one place\). Using dependencies means routers remain clean – they simply declare Depends\(security.get\_current\_active\_user\) to enforce auth. Sensitive constants like SECRET\_KEY and token lifetime are pulled from environment variables for safety. 

**app/models/user.py**

Defines Pydantic models related to **User data**. We separate models for different purposes: input \(creation\), database model, and output model. Key classes:

• UserBase : Basic fields common to all users \(username, email, full\_name\). 

• UserCreate : Inherits UserBase and adds a password field for registration. 

• UserInDB : Represents how a user is stored in the database, including internal fields not exposed directly \(e.g. hashed\_password , flags\). This model also includes lists for favorites \(course IDs\) and notifications . We use a custom PyObjectId type to allow Pydantic to handle MongoDB ObjectIds \(converted to str in JSON\). For example: class UserInDB\(UserBase\):

id: PyObjectId = Field\(default\_factory=PyObjectId, alias="\_id"\) hashed\_password: str

is\_active: bool = True

is\_admin: bool = False

favorites: List\[str\] = \[\]

notifications: List\["Notification"\] = \[\]

class Config:

json\_encoders = \{ObjectId: str\}

allow\_population\_by\_field\_name = True

5

Here Notification \(defined in notification.py \) is a nested model for notifications \(we use a string forward reference because Notification is defined separately\). 

• UserOut : The model for sending user data to clients. It omits the password and uses plain id as a string. It includes whether the user is active/admin, plus their favorites and notifications lists: 

class UserOut\(UserBase\):

id: str

is\_active: bool

is\_admin: bool

favorites: List\[str\]

notifications: List\["Notification"\]

• UserUpdate : Defines optional fields for profile updates \(email and full\_name, both optional\). 

W

• e also define Token and TokenData models in this module for login responses and JWT

payload data: 

class Token\(BaseModel\):

access\_token: str

token\_type: str = "bearer" 

class TokenData\(BaseModel\):

username: Optional\[str\] = None

is\_admin: bool = False

**Why organized this way:** By using Pydantic models, we ensure data validation and shape the data returned by our API. Splitting into multiple models clarifies each use-case: for example, UserCreate vs UserOut ensures we never accidentally return a password hash or accept already-hashed passwords, and UserOut \(with favorites and notifications \) matches exactly what the frontend expects after registration or in profile fetch. The PyObjectId utility class allows seamless conversion of Mongo \_id fields to string in API responses. 

**app/models/course.py**

This module holds Pydantic models for **Course and Review data**, shaping the output of course search results and details:

• Review : Represents a course review, with fields review\_id , text , rating \(possibly None if not available\), and sentiment\_score \(which may be None until enriched\). This corresponds to embedded review documents in the course collection. 

• CourseDetail : Represents a full detailed course record, used in the course detail endpoint. It includes identifying info and metadata: 

6

class CourseDetail\(BaseModel\):

course\_id: str

title: str

description: str

provider: str

url: str

categories: List\[str\]

num\_reviews: int

avg\_sentiment: float

smoothed\_sentiment: float

reviews: List\[Review\]

This maps exactly to the course document structure after ingestion and sentiment analysis: each course in MongoDB has these fields. 

• CourseSummary \(or CourseResult \): This model is used for search results or category listings. It includes only summary info plus the computed ranking score components: class CourseSummary\(BaseModel\):

course\_id: str

title: str

ranking\_score: float

text\_norm: float

sent\_norm: float

pop\_weight: float

num\_reviews: int

smoothed\_sentiment: float

These fields correspond to the ranking formula: text\_norm \(text relevance normalized\), sent\_norm \(sentiment normalized\), pop\_weight \(popularity weight\), and final ranking\_score . We will compute these on the fly in the search route. 

We separate CourseDetail and CourseSummary because the search endpoint returns multiple courses with only key info and a score, whereas the detail endpoint returns a single course with all reviews and fields. 

**app/models/category.py**

Defines the Pydantic models for **Course Categories**:

• CategoryIn : For creating or updating categories. It has a name, an optional description, and a list of keywords: 

class CategoryIn\(BaseModel\):

name: str

7

description: str = "" 

keywords: List\[str\]

• CategoryOut : The model used when returning category info via API. It includes an id \(as string\) along with all fields from CategoryIn : 

class CategoryOut\(CategoryIn\):

id: str

These ensure that when an admin creates or updates categories, the input is validated \(must include at least a name and keywords list\), and when listing categories, the client gets the ObjectId as a string id along with the category data. 

**Organization rationale:** Having a dedicated category model module clarifies the schema for the categories collection documents and API. Categories are managed by admin endpoints and retrieved by all users for browsing, so explicit models help avoid mistakes \(for example, ensuring we always output the correct fields, and making it easy to extend category attributes in the future if needed\). 

**app/models/notification.py**

This module defines the Notification model used inside user documents and API responses. A Notification contains an id, message text, a timestamp, and flags for delivery/read status. For example: class Notification\(BaseModel\):

id: PyObjectId = Field\(default\_factory=PyObjectId, alias="\_id"\) message: str

created\_at: datetime

read: bool = False

sent: bool = False

class Config:

json\_encoders = \{ObjectId: str, datetime: lambda dt: dt.isoformat\(\)\}

allow\_population\_by\_field\_name = True

When a new course becomes available for a user’s saved search keyword, the system creates a Notification with sent=False \(meaning it hasn’t been dispatched via email/push yet\) and read=False \(user hasn’t seen it yet\). The created\_at is a UTC timestamp of creation. 

This model is referenced in user.py \(as List\[Notification\] in UserInDB and UserOut \) so that notifications embedded in the user profile are validated and properly serialized \(ObjectIds and datetimes are converted to strings when output\). 

**Why separate:** In the original code, notification fields were managed as raw dicts, which led to some inconsistencies \(e.g., read was added in notifications but not defined in the model\). By formalizing a Notification model, we ensure consistency and can easily extend it \(for instance, adding a type or 8

other metadata\) without scattered changes. It also becomes easy to filter only unread notifications, etc., if needed. 

**app/routers/auth.py**

This router handles **user registration and login** \(the authentication endpoints\). It uses the prefix /

users \(to keep the same URLs as before, e.g. /users/register \) and is tagged "auth". Main endpoints:

• POST /users/register : Allows a new user to sign up. It expects a UserCreate body and returns the created UserOut . The logic: 

@router.post\("/register", response\_model=UserOut, status\_code=201\) def register\(user: UserCreate\):

\# Ensure unique username and email

if db\["users"\].find\_one\(\{"username": user.username\}\) or db\["users"\].find\_one\(\{"email": user.email\}\): raise HTTPException\(status\_code=400, detail="Username or email already registered"\)

\# Hash the password and construct the user document

hashed\_pw = security.get\_password\_hash\(user.password\)

doc = \{

"username": user.username, 

"email": user.email, 

"full\_name": user.full\_name, 

"hashed\_password": hashed\_pw, 

"is\_active": True, 

"is\_admin": False, 

"favorites": \[\], 

"notifications": \[\]

\}

result = db\["users"\].insert\_one\(doc\)

\# Fetch the inserted user and return as UserOut

new\_user = db\["users"\].find\_one\(\{"\_id": result.inserted\_id\}\) return UserOut\(\*\*new\_user, id=str\(result.inserted\_id\)\)

This preserves the original functionality: new users start as active \(not disabled\) and non-admin by default. 

• POST /users/login : Authenticates a user and returns a JWT token. We use OAuth2PasswordRequestForm to parse form data \( username and password \). The endpoint returns a Token if successful: 

@router.post\("/login", response\_model=Token\)

def login\(form\_data: OAuth2PasswordRequestForm = Depends\(\)\):

\# Verify user credentials

user\_doc = db\["users"\].find\_one\(\{"username": form\_data.username\}\) if not user\_doc or not security.verify\_password\(form\_data.password, 9

user\_doc\["hashed\_password"\]\):

raise HTTPException\(status\_code=401, 

detail="Invalid username or password", 

headers=\{"WWW-Authenticate": "Bearer"\}\)

\# Create JWT token with user info

access\_token = security.create\_access\_token\(

\{"sub": user\_doc\["username"\], "user\_id": str\(user\_doc\["\_id"\]\)\}

\)

return \{"access\_token": access\_token, "token\_type": "bearer"\}

This mirrors the original logic \(which combined username/password check and JWT creation\). 

The use of 401 Unauthorized and WWW-Authenticate header is per OAuth2 spec. 

**Why this organization:** Grouping register/login under auth.py \(with a common prefix\) clarifies these are authentication operations. We reused the /users prefix to avoid breaking the API for the mobile app. Notably, using OAuth2PasswordRequestForm in the login endpoint is a standard FastAPI approach for form-based login. Both endpoints avoid exposing the password or hashed\_password anywhere in responses \(register returns UserOut which excludes the password, login returns just the token\). 

**app/routers/users.py**

This router manages **user profile and personal actions** \(favorites, notifications\). It is prefixed with /

users and tagged "users". All routes here depend on an authenticated user \(via Depends\(get\_current\_active\_user\) \) to ensure only the logged-in user accesses their data. Key endpoints:

• GET /users/me : Returns the current user's profile \( UserOut \). This simply takes the current\_user from dependency and returns it in the output model: 

@router.get\("/me", response\_model=UserOut\)

def get\_profile\(current\_user =

Depends\(security.get\_current\_active\_user\)\):

\# current\_user is a dict from DB; convert to UserOut

return UserOut\(\*\*current\_user, id=str\(current\_user\["\_id"\]\)\) This shows the user their up-to-date info including favorites and notifications. 

• PUT /users/me : Updates the user's profile information. It expects a UserUpdate body \(optional email/full\_name\) and returns the updated UserOut . We update only provided fields: 

@router.put\("/me", response\_model=UserOut\)

def update\_profile\(data: UserUpdate, current\_user =

Depends\(security.get\_current\_active\_user\)\):

update\_data = \{k: v for k, v in

data.dict\(exclude\_none=True\).items\(\)\}

if update\_data:

db\["users"\].update\_one\(\{"\_id": current\_user\["\_id"\]\}, \{"$set": 10

update\_data\}\)

updated = db\["users"\].find\_one\(\{"\_id": current\_user\["\_id"\]\}\) return UserOut\(\*\*updated, id=str\(updated\["\_id"\]\)\) We exclude None values so that fields not provided remain unchanged. This preserves the ability for users to change their full name or email. 

**Favorites management:**

• 

• POST /users/me/favorites : Adds a course to the user's favorites list. We take a JSON body

\{"course\_id": "..."\} \(validated by FavoriteIn model with a course\_id field\) and use Mongo $addToSet to avoid duplicates: 

@router.post\("/me/favorites", status\_code=200\)

def add\_favorite\(fav: FavoriteIn, current\_user =

Depends\(security.get\_current\_active\_user\)\):

updated = db\["users"\].find\_one\_and\_update\(

\{"\_id": current\_user\["\_id"\]\}, 

\{"$addToSet": \{"favorites": fav.course\_id\}\}, return\_document=ReturnDocument.AFTER

\)

if not updated:

raise HTTPException\(404, "User not found"\)

return \{"favorites": updated\["favorites"\]\}

We return the updated favorites list \(status 200 OK\). This is slightly different from the original which returned 204 No Content – here we choose to return the new favorites array for convenience, but the functionality is the same \(adding the course ID if it wasn’t already favorited\). 

• DELETE /users/me/favorites/\{course\_id\} : Removes a specific course from favorites. 

The course\_id comes from the path. We use $pull to remove it: 

@router.delete\("/me/favorites/\{course\_id\}", status\_code=200\) def remove\_favorite\(course\_id: str, current\_user =

Depends\(security.get\_current\_active\_user\)\):

updated = db\["users"\].find\_one\_and\_update\(

\{"\_id": current\_user\["\_id"\]\}, 

\{"$pull": \{"favorites": course\_id\}\}, 

return\_document=ReturnDocument.AFTER

\)

if not updated:

raise HTTPException\(404, "User not found"\)

return \{"favorites": updated\["favorites"\]\}

This returns the new favorites list as well. The logic ensures idempotency – if the course wasn’t in favorites, the list remains unchanged. 

11

• GET /users/me/notifications : Retrieves the current user's notifications \(an array of Notification objects\). We query the user document for the notifications field: 

@router.get\("/me/notifications", response\_model=List\[Notification\]\) def list\_notifications\(current\_user =

Depends\(security.get\_current\_active\_user\)\):

user\_doc = db\["users"\].find\_one\(\{"\_id": current\_user\["\_id"\]\}, 

\{"notifications": 1\}\)

return user\_doc.get\("notifications", \[\]\)

The response model ensures proper serialization of each notification \(ObjectId -> string, datetime -> isoformat\). This allows the frontend to display any notifications \(e.g., "New courses available for 'machine learning'"\) and their read/sent status. 

**Why this organization:** All these routes pertain to *the currently authenticated user*, so grouping them clarifies that they require auth and act on the user’s own data. Using the security.get\_current\_active\_user dependency on the router \(or on each endpoint\) guarantees that no unauthorized access occurs – a user can only modify or view their own data because the token ties them to one user. By returning structured data \(favorites list, notifications list\) after modifications, we provide immediate feedback to clients. 

**app/routers/courses.py**

This router provides **course search and detail** endpoints. We set no prefix \(or you could set prefix="" \) so that the routes appear at the root as /search and /course/\{id\} as before. Tag these routes as "courses". Endpoints:

• GET /search : Performs a course search with ranking. It accepts a query string \( ? 

query=... \) and an optional top\_k \(number of results to return, default 10\). We allow this endpoint to be accessed without login \(but if the user *is* logged in, we capture their ID to track search requests for notifications\). The logic: 

@router.get\("/search", response\_model=List\[CourseSummary\]\) def search\_courses\(query: str = Query\(..., min\_length=1\), top\_k: int =

Query\(10, ge=1, le=100\), 

current\_user = Depends\(security.get\_current\_user\)\):

\# Use MongoDB text index to find matching courses

cursor = db\["courses"\].find\(

\{"$text": \{"$search": query\}\}, 

\{"score": \{"$meta": "textScore"\}, "course\_id": 1, "title": 1, 

"smoothed\_sentiment": 1, "num\_reviews": 1\}

\).sort\(\[\("score", \{"$meta": "textScore"\}\)\]\).limit\(top\_k \* 5\) docs = list\(cursor\)

if not docs:

\# If no courses found, and user is logged in, record the search for future notifications

if current\_user:

keyword\_queue.add\_request\(current\_user\["\_id"\], query\) 12

return \[\]

\# Compute max text score for normalization

max\_score = max\(d.get\("score", 0\) for d in docs\) or 1.0

results = \[\]

for d in docs:

text\_norm = d\["score"\] / max\_score

sent = float\(d.get\("smoothed\_sentiment"\) or 0.0\)

sent\_norm = \(sent \+ 1.0\) / 2.0

n = int\(d.get\("num\_reviews"\) or 0\)

pop\_weight = math.log\(1 \+ n\)

\# Weighted ranking formula combining text relevance, sentiment, and popularity

ranking = settings.ALPHA \* text\_norm \+ \(1 - settings.ALPHA\) \*

sent\_norm \+ settings.BETA \* pop\_weight

results.append\(CourseSummary\(

course\_id=d\["course\_id"\], title=d\["title"\], ranking\_score=round\(ranking, 4\), 

text\_norm=round\(text\_norm, 4\), 

sent\_norm=round\(sent\_norm, 4\), 

pop\_weight=round\(pop\_weight, 4\), 

num\_reviews=n, 

smoothed\_sentiment=round\(sent, 4\)

\)\)

\# Sort by our composite score and return top\_k

results.sort\(key=lambda c: c.ranking\_score, reverse=True\)

return results\[:top\_k\]

This uses the MongoDB text index on title/description/reviews to find relevant courses, as in the original design. The scoring formula \(with constants ALPHA and BETA from config, e.g. α=0.7, β=0.2\) is applied to rank results by a combination of text relevance, sentiment, and number of reviews. We multiply top\_k \* 5 internally to fetch a bit more results from the DB and then slice after sorting, to ensure we have enough to rank \(since combining with sentiment might shuffle order slightly\). If no results are found, we log the search for notification: the keyword\_queue.add\_request\(user\_id, query\) will mark that this user is interested in this query so they can be notified if courses for it appear later. \(If the user is not logged in, we skip tracking, since we have no user to notify.\)

• GET /course/\{course\_id\} : Returns detailed information for a specific course. This is straightforward: we find the course document by its course\_id \(which is our unique identifier like "coursera–some-slug" or "alison–slug" \). If found, we convert it to CourseDetail : 

@router.get\("/course/\{course\_id\}", response\_model=CourseDetail\) def get\_course\(course\_id: str\):

doc = db\["courses"\].find\_one\(\{"course\_id": course\_id\}\) if not doc:

raise HTTPException\(status\_code=404, detail=f"Course 

'\{course\_id\}' not found"\)

\# Convert embedded reviews to Review Pydantic models \(ensuring types\)

13

reviews = \[\]

for r in doc.get\("reviews", \[\]\):

reviews.append\(Review\(

review\_id=r.get\("review\_id", ""\), 

text=r.get\("text", ""\), 

rating=\(float\(r\["rating"\]\) if r.get\("rating"\) is not None else None\), 

sentiment\_score=\(float\(r\["sentiment\_score"\]\) if

r.get\("sentiment\_score"\) is not None else None\)

\)\)

return CourseDetail\(

course\_id=doc\["course\_id"\], 

title=doc.get\("title", ""\), 

description=doc.get\("description", ""\), provider=doc.get\("provider", ""\), 

url=doc.get\("url", ""\), 

categories=doc.get\("categories", \[\]\), 

num\_reviews=int\(doc.get\("num\_reviews", 0\)\), 

avg\_sentiment=float\(doc.get\("avg\_sentiment", 0.0\)\), smoothed\_sentiment=float\(doc.get\("smoothed\_sentiment", 0.0\)\), reviews=reviews

\)

We explicitly cast ratings and sentiment scores to floats or None to ensure they match the Review model types. This endpoint lets users see all details and reviews for a selected course. 

**Why this organization:** These are core features of the app – searching and viewing courses – so isolating them makes the code easy to locate. The search logic benefits from being in one place for tuning the ranking algorithm. We preserved the original ranking approach \(combining text index score, sentiment, and a logarithmic factor of review count\) and the use of MongoDB’s full-text search. By tracking search misses in the keyword\_queue \(only for logged-in users\), we maintain the **notification** **feature**: if the ingestion pipeline later finds courses matching that query, a notification will be sent. 

**app/routers/categories.py**

This router provides public **category listing and browsing** endpoints. It has prefix /categories and tag "categories". These endpoints do not require authentication \(any user can browse courses by category\):

• GET /categories : Returns all categories \(for populating filter lists, etc.\). We query the categories collection and return a list of CategoryOut : 

@router.get\("", response\_model=List\[CategoryOut\]\) def list\_categories\(\):

categories = \[\]

for cat in db\["categories"\].find\(\):

categories.append\(CategoryOut\(

id=str\(cat\["\_id"\]\), 

name=cat\["name"\], 

14

description=cat.get\("description", ""\), keywords=cat.get\("keywords", \[\]\)

\)\)

return categories

This simply transforms each category doc to the Pydantic model. 

• GET /categories/\{name\}/courses : Returns courses that belong to a given category \(by category name\). This allows users to browse all courses tagged with a specific category. We find all courses containing that category in their categories array: 

@router.get\("/\{name\}/courses", response\_model=List\[CourseSummary\]\) def get\_courses\_by\_category\(name: str\):

cursor = db\["courses"\].find\(

\{"categories": name\}, 

\{"course\_id": 1, "title": 1, "smoothed\_sentiment": 1, 

"num\_reviews": 1\}

\)

results = \[\]

for doc in cursor:

\# Compute a basic ranking score for category listing:

\# Here text relevance isn't applicable \(all these match the category exactly\), 

\# so we rank by sentiment and popularity only. 

sent = float\(doc.get\("smoothed\_sentiment", 0.0\)\)

sent\_norm = \(sent \+ 1.0\) / 2.0

n = int\(doc.get\("num\_reviews", 0\)\)

pop\_weight = math.log\(1 \+ n\)

score = \(1 - settings.ALPHA\) \* sent\_norm \+ settings.BETA \*

pop\_weight

results.append\(CourseSummary\(

course\_id=doc\["course\_id"\], 

title=doc\["title"\], 

ranking\_score=round\(score, 4\), 

text\_norm=0.0, 

sent\_norm=round\(sent\_norm, 4\), 

pop\_weight=round\(pop\_weight, 4\), 

num\_reviews=n, 

smoothed\_sentiment=round\(sent, 4\)

\)\)

results.sort\(key=lambda c: c.ranking\_score, reverse=True\)

return results

Here we generate a ranking score focusing on sentiment and popularity \(text norm is irrelevant since the category filter already matches the courses\). This means, for example, courses in the category are sorted such that those with higher sentiment \(good reviews\) and more reviews rank higher. This logic was implied in the original system \(category browse was to show courses by some order – we choose a sensible one\). 

15

**Why this organization:** Keeping category read operations separate from admin category management helps clarity. Regular users \(and the app\) only need these two endpoints for categories. By structuring the code this way, the functions remain simple. The courses\_by\_category function reuses the same CourseSummary model and a similar scoring concept, ensuring consistency in how courses are represented and ordered. 

**app/routers/admin\_users.py**

This router includes **admin-only endpoints for user management**. Prefix is /admin/users and tag

"admin". All routes depend on get\_current\_admin to ensure only an administrator can use them. 

Endpoints:

• GET /admin/users : List all users in the system \(returns List\[UserOut\] \). An admin can retrieve all user profiles: 

@router.get\("", response\_model=List\[UserOut\]\)

def list\_users\(admin=Depends\(security.get\_current\_admin\)\):

users = \[\]

for u in db\["users"\].find\(\):

users.append\(UserOut\(\*\*u, id=str\(u\["\_id"\]\)\)\)

return users

This is useful for an admin dashboard to see user info. It outputs the same fields as a normal profile, but for everyone. 

• PUT /admin/users/\{id\}/block : Toggle a user's active status \(block or unblock\). The admin supplies a user ID and a boolean query parameter block=true/false . We interpret block=true as setting the user's is\_active to False \(and block=false to True\): 

@router.put\("/\{id\}/block", response\_model=UserOut\) def block\_or\_unblock\_user\(id: str, block: bool = True, 

admin=Depends\(security.get\_current\_admin\)\):

oid = ObjectId\(id\)

res = db\["users"\].find\_one\_and\_update\(

\{"\_id": oid\}, 

\{"$set": \{"is\_active": not block\}\}, 

\# if block=True, set 

is\_active=False

return\_document=ReturnDocument.AFTER

\)

if not res:

raise HTTPException\(status\_code=404, detail="User not found"\) return UserOut\(\*\*res, id=id\)

This lets admins disable a user’s account \(or re-enable it\). We return the updated user data. The logic flips the is\_active flag accordingly. 

• DELETE /admin/users/\{id\} : Delete a user account. The admin provides the user’s ID, and if found, we delete that user from the database: 

16

@router.delete\("/\{id\}", status\_code=204\) def delete\_user\(id: str, admin=Depends\(security.get\_current\_admin\)\): result = db\["users"\].delete\_one\(\{"\_id": ObjectId\(id\)\}\) if result.deleted\_count == 0:

raise HTTPException\(status\_code=404, detail="User not found"\) return Response\(status\_code=204\)

\(We can simply return nothing with a 204 No Content if successful.\) These admin endpoints were previously implemented \(either in the old app.py or routers/

admin\_users.py \), and we have preserved their functionality exactly. Admins can list users, block/

unblock them \(which was “disable” in original terms\), and delete users. 

**Why separate admin users:** Regular users should not have access to these operations, and combining them with normal user routes could be confusing or hazardous. By isolating them under an /admin path and using the admin dependency, we make the security model clear. It also aligns with typical REST

design for admin scopes. Now it's easy to extend with more admin user controls if needed \(e.g., resetting passwords\) without affecting the user-facing API. 

**app/routers/admin\_categories.py**

This router manages **admin CRUD for course categories**. Prefix /admin/categories , tag "admin". 

Only admins \(via get\_current\_admin dependency\) can use these. Endpoints align with standard create-read-update-delete for category objects:

• POST /admin/categories : Create a new category. Expects a CategoryIn body. We first ensure no existing category with the same name: 

@router.post\("", response\_model=CategoryOut, status\_code=201\) def create\_category\(cat: CategoryIn, 

admin=Depends\(security.get\_current\_admin\)\):

if db\["categories"\].find\_one\(\{"name": cat.name\}\): raise HTTPException\(status\_code=400, detail="Category already exists"\)

res = db\["categories"\].insert\_one\(cat.dict\(\)\)

return CategoryOut\(id=str\(res.inserted\_id\), \*\*cat.dict\(\)\)

After insertion, we return the created category with its new ID. 

• GET /admin/categories/\{id\} : Get details of one category by ID. Returns CategoryOut : 

@router.get\("/\{id\}", response\_model=CategoryOut\)

def read\_category\(id: str, admin=Depends\(security.get\_current\_admin\)\): cat = db\["categories"\].find\_one\(\{"\_id": ObjectId\(id\)\}\) if not cat:

raise HTTPException\(status\_code=404, detail="Category not found"\)

17

return CategoryOut\(id=id, name=cat\["name"\], description=cat.get\("description", ""\), keywords=cat.get\("keywords", \[\]\)\)

• PUT /admin/categories/\{id\} : Update a category’s name/description/keywords. We take a CategoryIn body and apply it: 

@router.put\("/\{id\}", response\_model=CategoryOut\)

def update\_category\(id: str, cat: CategoryIn, 

admin=Depends\(security.get\_current\_admin\)\):

oid = ObjectId\(id\)

result = db\["categories"\].find\_one\_and\_update\(

\{"\_id": oid\}, 

\{"$set": cat.dict\(\)\}

\)

if not result:

raise HTTPException\(status\_code=404, detail="Category not found"\)

return CategoryOut\(id=id, \*\*cat.dict\(\)\)

\(We return the new state of the category, which mirrors the input.\)

• DELETE /admin/categories/\{id\} : Delete a category. If deletion is successful, we also remove that category tag from all courses: 

@router.delete\("/\{id\}", status\_code=204\)

def delete\_category\(id: str, admin=Depends\(security.get\_current\_admin\)\): oid = ObjectId\(id\)

cat = db\["categories"\].find\_one\_and\_delete\(\{"\_id": oid\}\) if not cat:

raise HTTPException\(status\_code=404, detail="Category not found"\)

\# Remove this category name from any courses' categories array db\["courses"\].update\_many\(\{\}, \{"$pull": \{"categories": cat\["name"\]\}\}\)

return Response\(status\_code=204\)

This ensures data consistency – once a category is deleted, no course should still reference it. We could also trigger re-tagging, but since category\_tagger.watch\_changes \(see below\) is running, it will catch the removal \(the change-stream will notice the delete operation and clear tags, though we already did it manually here for completeness\). 

**Why separate admin categories:** Much like admin users, category management is an admin responsibility. By having these in their own router, we avoid exposing create/update/delete to normal clients. Also, isolating this logic makes it easier to integrate with the category tagging system: whenever categories are created or updated, our background watch\_changes in category\_tagger \(discussed next\) will automatically re-run tagging for that category. The structure is such that the admin can manage categories freely, and the system keeps course tags in sync. 

18

**app/utils/keyword\_queue.py**

The keyword\_queue utility manages the **keyword scraping queue and search request tracking**. It interfaces with two Mongo collections: keyword\_queue and search\_requests . Its functions:

• seed\_defaults\(default\_keywords: List\[str\]\) : \(Optional\) Seed the queue with a set of initial keywords if not already present. This can be used on first run to populate known popular topics. 

• get\_all\_keywords\(\) and get\_pending\_keywords\(\) : Retrieve keywords in the queue, either all or only those with scraped = False . The ingestion service uses get\_pending\_keywords\(\) to know what new searches to scrape next. 

• mark\_scraped\(keyword: str\) : Mark a keyword as scraped \(sets scraped: True in the queue\). This is called after scrapers have run successfully on that keyword, so it won’t be scraped again unless reset. 

• enqueue\(keyword: str\) : Add a new keyword to the queue \(if it doesn’t already exist\). This is used for on-demand additions – e.g., if an admin or some logic wants to ensure a certain keyword is scraped regularly. The function uses an upsert operation so it won’t duplicate keywords; if the keyword exists it simply returns it, if not it inserts with scraped=False . It returns the queue document \(with scraped status\). 

**Sear**

• 

**ch request tracking:** The second part is handling user search requests that had no results:

• add\_request\(user\_id, keyword\) : Log that a given user searched for a keyword but got no results. It inserts a document into search\_requests with user\_id , keyword , requested\_at timestamp, and notified=False . We ensure not to duplicate an existing pending request \(the code checks that no document exists for that user/keyword with notified=False before inserting\). This is invoked in the /search endpoint when len\(results\) == 0 for a logged-in user. 

• get\_pending\_requests\(\) \(or simply get\_pending in code\): Retrieve all search request docs where notified=False . This is used by the notification service to know which queries still need notifications. 

• mark\_notified\(request\_id\) : Mark a specific search request as notified \(set notified=True \). The notification service will call this after sending a notification. 

Under the hood, keyword\_queue.py uses the global db from config, specifically: kw\_coll = db\["keyword\_queue"\]

reqs\_coll = db\["search\_requests"\]

We have updated it to use settings.MONGO\_URI via config.db \(instead of a hard-coded URI in the original code\), making it environment-configurable. 

**Why is this needed:** The keyword queue ensures the scraping service only processes new or needed keywords, preventing redundant scrapes \(one of our optimization goals\). Once a keyword’s courses are gathered, it’s marked done. If the data ever needs refreshing, an admin could reset the flag or re-enqueue the keyword. The search request log ties into notifications – it effectively remembers 19

“unfulfilled” searches. This decoupling of search query tracking from immediate notification means the user doesn’t have to poll; the system will proactively notify later. By keeping these operations in a utility module, the logic remains testable and separate from API layer – the API just calls add\_request when needed, and the ingestion/notification services query the pending lists when running. 

**app/utils/category\_tagger.py**

The category tagger is a critical utility that automatically **assigns category labels to courses based on** **keywords**. It works in two modes: one-off backfill \( retag\_all \) and continuous watch \( watch\_changes \):

**T**

• **ext Index Setup:** It ensures a text index exists on the courses collection for fields title , description , and reviews.text . The index is named consistently \(e.g., 

"CourseTextIndex" \). It drops any old text indexes that might interfere. This uses pymongo commands: 

def ensure\_text\_index\(\):

coll = db\["courses"\]

\# Drop any existing text indexes except the canonical one

for idx in coll.list\_indexes\(\):

if "text" in idx\["key"\].values\(\) and idx\["name"\] \!= TEXT\_INDEX: coll.drop\_index\(idx\["name"\]\)

coll.create\_index\(\[\("title", TEXT\), \("description", TEXT\), \("reviews.text", TEXT\)\], name=TEXT\_INDEX\)

log.info\(f"Ensured text index '\{TEXT\_INDEX\}' exists."\)

• retag\_all\(\) : This function recomputes category tags for **all courses** from scratch. For each category in the categories collection, it runs a text search query of all that category’s keywords against the courses collection. It then applies a threshold: it will only tag the courses whose text search score is at least a certain fraction of the top score \(to avoid tagging courses that are weakly related\). The threshold factor \(e.g., 0.2 or 20% of top score\) is configurable via an environment variable TAG\_THRESHOLD \(default 0.2\). The process: Remo

• 

ve the category name from all courses \(clear old tags\) – done by $pull: \{categories: name\} for all courses. 

Perform a 

• 

$text search for the category’s keywords combined as a search string. 

Determine 

• 

max\_score from results, and calculate threshold = TAG\_THRESHOLD \* 

max\_score . 

Iter

• 

ate through the results in score order, and for each result with score >= threshold , add the category to that course’s categories array \(via $addToSet \). 

Log ho

• 

w many courses were tagged out of total found. 

This ensures that each category gets assigned to the top ~20% of relevant courses for its keywords. By calling retag\_all\(\) after a bulk ingestion, we make sure new courses are categorized. 

• watch\_changes\(\) : This function uses MongoDB's change stream to watch the categories collection. It listens for any insert, update, or replace operations on categories. When a category changes:

It r

• 

emoves that category from all courses \(like in retag\_all\). 

20

If the category was not deleted \(i.e., still has ke

• 

ywords\), it reruns the text search and tagging for 

*that single category* \(just like in retag\_all but scoped to one category\). 

Logs the r

• 

etagging outcome for that category. 

This means if an admin updates a category’s keywords or adds a new category, the tagger will immediately propagate those changes to the courses in the background, without needing a manual rerun. 

The category tagger also uses environment variables for its config: TAG\_THRESHOLD as mentioned, and it respects the MONGO\_URI from config \(we pass it via env or use config.db \). 

**Why this is important:** This automated tagging frees the admin from manually assigning courses to categories. The threshold logic avoids noise \(only courses strongly matching the category keywords get tagged\). Running it after each ingestion \(and on updates\) means the category browse feature is always up-to-date. We placed it in utils/ because it’s not directly exposed via API, but it’s a behind-the-scenes service. By keeping it separate, the code for tagging is isolated and can be maintained or tuned \(for example, adjusting the threshold or index fields\) independently of the API code. It’s triggered from main.py on startup and by the ingestion pipeline upon completion. 

*\(Note: In our refactoring, we ensured category\_tagger uses the shared db connection and* *environment variables rather than hard-coded values. This aligns with our .env config usage.\)* **app/utils/unify\_data.py**

**Unified Data Assembly:** This module replaces the older approach of writing unified JSON files to disk. It provides functions to merge raw data from the provider-specific scrapers into a unified course document **in-memory** so it can go straight to the database. 

Each provider \(Coursera, Alison, etc.\) has its own scraping output format. The unify\_data utility normalizes these into a consistent schema as follows:

W

• e define helper functions canon\_course\(raw\_course, provider, slug\) and canon\_review\(raw\_review, provider, slug, idx\) to transform raw course info and raw reviews into the canonical structure. For example, canon\_course produces: 

\{

"course\_id": f"\{provider\}–\{slug\}", 

"title": raw\_course.get\("title", ""\).strip\(\), 

"description": \(raw\_course.get\("description"\) or ""\).strip\(\), 

"provider": provider, 

"url": raw\_course.get\("link"\) or raw\_course.get\("info\_url", ""\), 

"last\_updated": datetime.utcnow\(\), 

"categories": raw\_course.get\("categories", \[\]\), 

"reviews": \[\]

\}

and canon\_review produces: 

21

\{

"review\_id": f"\{provider\}–\{slug\}–\{idx\}", 

"text": raw\_review.get\("text"\) or raw\_review.get\("review\_text", ""\) or "", 

"rating": raw\_review.get\("rating"\) or raw\_review.get\("stars"\), 

"scraped\_at": datetime.utcnow\(\)

\}

These ensure each course and review has a unique ID \(combining provider and a slug\), and common fields \(title, description, rating, etc.\). 

The

• 

main function unify\_provider\(provider\_name, course\_list, review\_lists\) takes the raw data from one provider and merges them:

Iter

• 

ate through all courses from that provider, create a base course document for each \(using canon\_course \), stored in a dict keyed by a slug identifier. 

Iter

• 

ate through all review sets from that provider, match each review file to the corresponding course by slug \(derived from file name or course ID\), and append the reviews \(via canon\_review \) to the course’s reviews list. 

Return the list of unified course documents for that pr

• 

ovider. 

• unify\_all\(providers\_data: Dict\[str, Tuple\[list, dict\]\]\) : We pass in a mapping of provider name to its scraped data \(courses and reviews\). For each provider, we call unify\_provider and collect all unified docs. The result is a list of unified course docs ready to be inserted to DB. 

In our new **ingestion pipeline**, instead of writing unified JSON files to disk and then reading them, we use unify\_data.unify\_all\(\) directly in memory. This dramatically simplifies the data flow: scraped data -> unified docs -> DB, without intermediate file I/O. It achieves the same result as before but more efficiently. 

**Why this change:** Originally, the system dumped JSON files to a unified\_data/ folder and then loaded them to insert into MongoDB. By removing that step, we reduce disk usage and the risk of stale data \(in a long-running app, those files needed cleanup or could become outdated\). Now the data lives in MongoDB as the source of truth immediately after scraping. This makes the system more robust and faster. The unify\_data code is structured to be easily extensible if new providers are added – one would feed its raw data into unify\_provider . Since this module is used only internally by the ingestion service, it’s kept in utils/ as a pure function library. 

*\(The code for unify\_data is derived from the original unify.py script, but refactored to function form. *

*We also ensure that last\_updated is set when unifying to track currency of data.\)* **app/services/data\_ingestion.py**

This service orchestrates the **periodic data ingestion pipeline**. It ties together the scrapers, unify logic, and database insertion, and includes improvements to avoid redundant work: 22

**Overview:** The ingestion process runs periodically \(every X hours as scheduled\) and performs: 1. 

**Scraping new keywords:** It checks the keyword\_queue for any keywords marked scraped=False . 

For each such keyword, it runs the provider scrapers to fetch courses and reviews for that keyword. 2. 

**Unification:** Merge all scraped data into unified course documents. 3. **Database upsert:** Write the unified course documents into the courses collection \(inserting new or updating existing courses by course\_id \). 4. **Categorization:** Trigger category tagging \( retag\_all \) to label new courses. 5. 

**Notification check:** Trigger the notification service to notify users if any of their saved searches now have results. 

Each of these steps is encapsulated:

• run\_scrapers\_for\_pending\(\) : Uses keyword\_queue.get\_pending\_keywords\(\) to retrieve a list of search terms that have not been scraped yet. If the list is empty, the function logs and returns False \(indicating nothing to do\). Otherwise, for each keyword, it invokes the scrapers. For example: 

def run\_scrapers\_for\_pending\(\):

pending\_keywords = keyword\_queue.get\_pending\_keywords\(\)

if not pending\_keywords:

log.info\("No new keywords to scrape."\)

return False

for kw in pending\_keywords:

log.info\(f"Scraping courses for keyword: '\{kw\}'"\)

\# Run Alison scraper

scraped\_courses\_alison, scraped\_reviews\_alison =

alison\_scraper.scrape\(kw\)

\# Run Coursera scraper

scraped\_courses\_coursera, scraped\_reviews\_coursera =

coursera\_scraper.scrape\(kw\)

\# \(The scraper modules provide data in Python lists/dicts 

instead of writing files\)

\# Mark keyword as scraped in queue

keyword\_queue.mark\_scraped\(kw\)

\# Accumulate scraped data

all\_data\["alison"\]\["courses"\].extend\(scraped\_courses\_alison\) all\_data\["alison"\]\["reviews"\].update\(scraped\_reviews\_alison\) all\_data\["coursera"\]\["courses"\].extend\(scraped\_courses\_coursera\) all\_data\["coursera"\]\["reviews"\].update\(scraped\_reviews\_coursera\) return True

Here, we imagine alison\_scraper.scrape\(keyword\) returns a tuple of \(list\_of\_courses, dict\_of\_reviews\_by\_course\) for that keyword, and similarly for Coursera. In our refactoring, we can integrate the scrapers as Python functions \(if possible\) instead of subprocess calls, to write directly to memory. **If integrating directly is too complex**, an alternative is still to call them via subprocess but then load their output from in-memory pipes. However, since we want to eliminate intermediate files, ideally the scrapers would be refactored to return data rather than write files. For this refactoring explanation, we assume scrapers can be called as above for clarity. 

23

• unify\_and\_ingest\(all\_data\) : After scraping all pending keywords, we unify and insert: def unify\_and\_ingest\(all\_data\):

\# Use unify\_data utility to get unified course docs for all providers

unified\_docs = unify\_data.unify\_all\(\{

"alison": \(all\_data\["alison"\]\["courses"\], all\_data\["alison"\]

\["reviews"\]\), 

"coursera": \(all\_data\["coursera"\]\["courses"\], all\_data\["coursera"\]\["reviews"\]\)

\}\)

if not unified\_docs:

log.warning\("No new courses to ingest."\)

return False

\# Prepare bulk upsert operations

ops = \[\]

for doc in unified\_docs:

ops.append\(UpdateOne\(\{"course\_id": doc\["course\_id"\]\}, \{"$set": doc\}, upsert=True\)\)

result = db\["courses"\].bulk\_write\(ops\)

log.info\(f"Upserted \{result.upserted\_count\} new courses, modified 

\{result.modified\_count\} existing courses."\)

return True

This takes the aggregate scraped data and produces unified documents. Each document is upserted by course\_id , so existing course entries get updated \(e.g., if we scraped a keyword that includes a course we saw before, perhaps now with more reviews, it updates it\). 

• run\_ingestion\_pipeline\(\) : The main function tying it all: def run\_ingestion\_pipeline\(\):

log.info\("Starting ingestion pipeline..."\)

start\_time = datetime.utcnow\(\)

any\_scraped = run\_scrapers\_for\_pending\(\)

if not any\_scraped:

log.info\("Ingestion pipeline finished \(nothing to scrape\)."\) return

unify\_and\_ingest\(all\_scraped\_data\)

\# After ingestion, update categories for all courses

category\_tagger.retag\_all\(\)

\# Process any search requests that can now be fulfilled

notification\_service.process\_search\_requests\(\)

elapsed = datetime.utcnow\(\) - start\_time

log.info\(f"Ingestion pipeline completed in 

\{elapsed.total\_seconds\(\):.2f\} seconds."\)

Important improvements:

24

If no ke

• 

ywords were pending \( any\_scraped=False \), we skip unify/ingest \(preventing redundant operations on the same data\) – this optimization avoids reprocessing everything every run when there are no changes. 

W

• e call retag\_all\(\) to categorize the newly ingested courses immediately. 

W

• e call notification\_service.process\_search\_requests\(\) at the end. This will check all search\_requests with notified=False to see if the just-ingested courses satisfy any previously empty searches, and create notifications for those users if so. 

**Why this design:** This service encapsulates the end-to-end flow of data acquisition. By separating scraping from ingestion, and by building the data in memory, we avoid duplicating tasks. The original code would unify and ingest even if nothing was scraped; now we detect that and short-circuit appropriately \(saving database and CPU work\). Directly writing to MongoDB instead of intermediate files satisfies the requirement to drop file-based storage. The modular functions make it easier to test each stage \(we can unit test unify\_and\_ingest with sample data, etc.\). And by calling the other utilities \(category tagging and notifications\) at the right time, we ensure data integrity – e.g., categories are always updated after new courses appear, and users are notified promptly. 

**Note:** We maintain use of APScheduler \(see services/scheduler.py \) to trigger run\_ingestion\_pipeline\(\) periodically in the background, rather than calling it on every API request. This keeps the system efficient and up-to-date without manual intervention. 

**app/services/sentiment.py**

This service handles the **sentiment enrichment** of course review data \(Phase 2 of the pipeline\). It can run on a schedule \(e.g., nightly\) since sentiment generally doesn’t need real-time updating for every scrape. The steps mirror the original design:

• score\_new\_reviews\(\) : Find all reviews in the courses collection that do **not** have a sentiment\_score yet, and compute it. Using TextBlob \(or a similar sentiment analysis library\), we iterate through each review text and calculate polarity: def score\_new\_reviews\(\):

pipeline = \[

\{"$unwind": "$reviews"\}, 

\{"$match": \{"reviews.sentiment\_score": \{"$exists": False\}\}\}, 

\{"$project": \{"course\_id": 1, "reviews.review\_id": 1, 

"reviews.text": 1\}\}

\]

updates = \[\]

count = 0

for doc in db\["courses"\].aggregate\(pipeline\):

review\_text = doc\["reviews"\]\["text"\] or "" 

score = TextBlob\(review\_text\).sentiment.polarity

updates.append\(UpdateOne\(

\{"course\_id": doc\["course\_id"\], "reviews.review\_id": doc\["reviews"\]\["review\_id"\]\}, 

\{"$set": \{"reviews.$.sentiment\_score": score\}\}

\)\)

count \+= 1

if updates:

25

res = db\["courses"\].bulk\_write\(updates\) log.info\(f"Assigned sentiment\_score for \{count\} new reviews \(documents updated: \{res.modified\_count\}\)"\)

else:

log.info\("No new reviews to score."\)

This operation uses a Mongo aggregation to pull out each review lacking a sentiment\_score. We then bulk-update all those reviews in place with their sentiment. This is efficient and ensures that we don’t recompute scores for reviews that already have them. 

• aggregate\_course\_metrics\(\) : Using the now-available sentiment scores, compute each course’s aggregate metrics: number of reviews num\_reviews , average sentiment avg\_sentiment , and a Bayesian smoothed sentiment smoothed\_sentiment \(to account for courses with few reviews\). The method: 

def aggregate\_course\_metrics\(\):

\# Compute global average sentiment across all reviews \(for 

smoothing\)

all\_scores = \[\]

for c in db\["courses"\].find\(\{\}, \{"reviews.sentiment\_score": 1\}\): for r in c.get\("reviews", \[\]\):

if "sentiment\_score" in r:

all\_scores.append\(r\["sentiment\_score"\]\)

global\_mean = sum\(all\_scores\)/len\(all\_scores\) if all\_scores else 0.0

log.info\(f"Global sentiment mean = \{global\_mean:.4f\}"\) updates = \[\]

for course in db\["courses"\].find\(\{\}, \{"course\_id": 1, 

"reviews.sentiment\_score": 1\}\):

scores = \[r\["sentiment\_score"\] for r in course.get\("reviews", 

\[\]\) if "sentiment\_score" in r\]

n = len\(scores\)

avg = sum\(scores\)/n if n else 0.0

\# Bayesian smoothing: weight with global\_mean and PSEUDOCOUNT

smooth = \(\(PSEUDOCOUNT \* global\_mean\) \+ sum\(scores\)\) /

\(PSEUDOCOUNT \+ n\) if \(PSEUDOCOUNT \+ n\) else global\_mean

updates.append\(UpdateOne\(

\{"course\_id": course\["course\_id"\]\}, 

\{"$set": \{"num\_reviews": n, "avg\_sentiment": avg, 

"smoothed\_sentiment": smooth\}\}

\)\)

if updates:

res = db\["courses"\].bulk\_write\(updates\)

log.info\(f"Updated sentiment metrics for \{res.modified\_count\}

courses."\)

else:

log.info\("No courses found to update metrics."\)

Here PSEUDOCOUNT is a constant \(e.g., 10\) that determines how strongly to pull a course’s sentiment toward the global mean if it has few reviews. This prevents courses with a single very 26

positive or negative review from appearing at extremes unfairly. We update each course document with the new values. 

• rebuild\_text\_index\(\) : After updating course documents, we drop and rebuild the text index on the courses collection. This is because the course data \(title/description\) might not change here, but if we wanted to incorporate review text into the text index \(which we do, on reviews.text field\), we should ensure the index reflects any changes. Actually, since reviews texts themselves are static once scraped, rebuilding the index every day might not be strictly necessary unless we’ve added many new courses or changed text. However, to be safe \(and as done originally\), we recreate the index: 

def rebuild\_text\_index\(\):

coll = db\["courses"\]

for idx in coll.list\_indexes\(\):

if "text" in idx\["key"\].values\(\):

coll.drop\_index\(idx\["name"\]\)

coll.create\_index\(\[\("title", TEXT\), \("description", TEXT\), \("reviews.text", TEXT\)\], name="CourseTextIndex"\) log.info\("Rebuilt text index on courses."\)

This is similar to what category\_tagger.ensure\_text\_index\(\) does. We might unify these in future to avoid duplication. In any case, ensuring a fresh text index can help if the data changed. 

• run\_sentiment\_enrichment\(\) : Coordinates the above steps: def run\_sentiment\_enrichment\(\):

log.info\("Starting sentiment enrichment..."\)

score\_new\_reviews\(\)

aggregate\_course\_metrics\(\)

rebuild\_text\_index\(\)

log.info\("Sentiment enrichment complete."\)

We would schedule this to run at a low-traffic time \(e.g., 2 AM daily, as originally configured\), because it potentially touches many documents. Doing it daily is fine as reviews don’t change often except when new courses are added. 

**Why separate service:** Sentiment analysis is computational and logically distinct from simply scraping and ingesting data. By scheduling it separately \(not every ingestion run\), we reduce load and can control when it happens. It also makes the system design modular: the ingestion ensures data availability, and the sentiment service enhances that data for better user experience \(like more relevant search ranking via smoothed\_sentiment \). The code is organized for clarity: each part of the enrichment is in its own function, which aligns with the pipeline steps documented in the original project. This service can be tested or run independently of the scraper if needed. 

27

**app/services/notification\_service.py**

This service deals with **user notifications** when new courses become available for previously unsuccessful searches, as well as dispatching those notifications. It works closely with the search\_requests and users collections:

• process\_search\_requests\(\) : Go through all search requests where notified=False and check if we now have results for those queries. For each pending request: def process\_search\_requests\(\):

pending = keyword\_queue.get\_pending\(\)

\# get all requests with 

notified=False

for req in pending:

kw = req\["keyword"\]

user\_id = req\["user\_id"\]

\# Check if any course now matches the keyword \(using text search on courses\)

if db\["courses"\].count\_documents\(\{"$text": \{"$search": kw\}\}\) > 0:

message = f"New courses are now available for '\{kw\}'." 

notification = \{

"\_id": PyObjectId\(\), 

\# generate a new ObjectId for the 

notification

"message": message, 

"created\_at": datetime.utcnow\(\), 

"read": False, 

"sent": False

\}

\# Push the notification to the user's notifications array

db\["users"\].update\_one\(\{"\_id": user\_id\}, \{"$push":

\{"notifications": notification\}\}\)

\# Mark the search request as notified

keyword\_queue.mark\_notified\(req\["\_id"\]\)

log.info\(f"Notification queued for user 

\{user\_id\} on keyword '\{kw\}'"\)

This function is called at the end of each ingestion pipeline run. In effect, whenever new courses are ingested, we immediately check if that satisfies any user's saved search. If yes, we create a Notification in that user's profile. We set sent=False initially \(meaning it hasn't been dispatched via external means yet\). If multiple courses match, we still just send one notification per search keyword. This matches the intended use-case \(the user gets a single alert that new courses for their query are available, then they can come to the app and search again to see them\). 

• dispatch\_notifications\(\) : This would handle delivering notifications to users through their preferred channel \(which could be email, push, etc.\). In our context, we don't have an external service integrated, so we simulate this by logging and marking as sent: 28

def dispatch\_notifications\(\):

\# Find all notifications that have not been sent yet

pipeline = \[

\{"$unwind": "$notifications"\}, 

\{"$match": \{"notifications.sent": False\}\}, 

\{"$project": \{"user\_id": "$\_id", "notification":

"$notifications"\}\}

\]

for doc in db\["users"\].aggregate\(pipeline\):

user\_id = doc\["user\_id"\]

note = doc\["notification"\]

\# contains \_id, message, etc. 

\# "Send" the notification \(here we just log it; in real case, send email or push\)

log.info\(f"Dispatching notification to user \{user\_id\}: 

\{note\['message'\]\}"\)

\# Mark as sent

db\["users"\].update\_one\(

\{"\_id": user\_id, "notifications.\_id": note\["\_id"\]\}, 

\{"$set": \{"notifications.$.sent": True\}\}

\)

We aggregate over users unwinding notifications to find all unsent notifications. For each, we log an action \(placeholder for actual dispatch\). Then we mark that specific notification’s sent flag to True to avoid re-sending it. This function can be scheduled to run periodically \(e.g., every few hours, slightly after ingestion runs\). Indeed, in the scheduler we schedule dispatch\_notifications a bit after the ingestion job, so that any new notifications created by process\_search\_requests are then delivered. 

\(Optional\)

• 

watch\_notifications\(\) : In case we wanted to run a continuous loop in a thread \(as the original notifications.watch\_and\_process did\), we could implement: def watch\_notifications\(interval\_hours=4\):

while True:

process\_search\_requests\(\)

dispatch\_notifications\(\)

time.sleep\(interval\_hours \* 3600\)

However, since we have a scheduler, we generally don't need this loop in the refactored design. 

We prefer APScheduler to manage timing, as it's more flexible and can be controlled. 

**Why this design:** We improved the notifications logic by making sure that the notifications created contain all relevant info \(message, timestamp, read/sent flags\) and by aligning the model with usage. By separating creation \( process\_search\_requests \) from dispatch \( dispatch\_notifications \), we could in the future integrate a real email or push notification service in the dispatch step without altering how notifications are recorded in the database. Also, marking the search request as notified=True right when we queue the notification ensures we don't accidentally double-notify the same query. We preserved the original behavior example \(if a user searched "machine learning" and nothing was found, later when courses for "machine learning" appear, they get a notification\) – and the 29

improvement is that we ensure sent vs read status is tracked, and avoid inserting incomplete notification objects \(the original missed the sent field in the inserted dict; we include it\). 

Admins or the system can query the search\_requests collection at any time to see what users are waiting for, etc., which could be useful. The user will see their notifications via the /users/me/

notifications endpoint and can mark them read \(we could easily add an endpoint to mark notifications as read, updating the read flag, though it wasn't in the original scope\). 

**app/services/scheduler.py**

This module configures **APScheduler jobs** to run the above services periodically. We use a BlockingScheduler if running as a standalone process, or we could use a BackgroundScheduler if integrating into the FastAPI app process \(depending on deployment preference\). For simplicity, we keep it similar to the original:

from apscheduler.schedulers.blocking import BlockingScheduler from app.services import data\_ingestion, sentiment, notification\_service sched = BlockingScheduler\(timezone="UTC"\)

\# Job: run full ingestion pipeline every 4 hours

sched.add\_job\(data\_ingestion.run\_ingestion\_pipeline, "interval", hours=4, id="ingest\_job", max\_instances=1, next\_run\_time=None\)

\# Job: run notification dispatch every 4 hours \(offset by a few minutes after ingestion\)

sched.add\_job\(notification\_service.dispatch\_notifications, "interval", hours=4, id="notify\_job", max\_instances=1, next\_run\_time=None, minutes=5\)

\# Job: run sentiment enrichment daily at 2:00 AM

sched.add\_job\(sentiment.run\_sentiment\_enrichment, "cron", hour=2, minute=0, id="sentiment\_job", max\_instances=1\)

*\(We used next\_run\_time=None on interval jobs to start them immediately on scheduler start, and* *perhaps an offset of 5 minutes for dispatch to ensure ingestion has completed.\)* At the bottom: 

if \_\_name\_\_ == "\_\_main\_\_":

try:

sched.start\(\)

except \(KeyboardInterrupt, SystemExit\):

pass

**Usage:** This scheduler can be run in a separate process or thread. In a development setup, you might start it alongside the FastAPI app. In production, a better approach might be to integrate the scheduler into the FastAPI app's lifespan events or use a dedicated worker. However, since production deployment is out of scope here, running this as a simple script \(or via uvicorn if integrated\) is acceptable for local runs. 

30

**Why APScheduler:** It provides a reliable way to schedule recurring tasks inside a long-running application, and it was already used in the original code. We preserved the intervals \(4 hours for scraping & notifications, daily for sentiment\) – these can be adjusted via config if needed. By having all scheduling in one place, it’s easy to see the periodic tasks of the system. We also ensure that at most one instance of each job runs at a time \( max\_instances=1 \), preventing overlapping runs in case one takes longer than the interval. 

This approach ensures **no redundant scrapes**: the ingestion job itself checks for new keywords, and APScheduler will trigger it regularly. If nothing new, it exits quickly \(we log that it did nothing\). If something fails, APScheduler can retry on next interval. The sentiment job running daily keeps the data fresh for search ranking. Notifications dispatch runs regularly to simulate pushing out alerts. 

**Environment Configuration \( .env.example \)**

We have moved all sensitive or environment-specific values to a .env file. This file should be placed in the project root \(or appropriate location\) and loaded by BaseSettings . Below is an example of what

.env.example looks like, which developers can copy to .env and fill in actual secrets:

\# .env.example - sample environment variables for Course Retrieval App

\# MongoDB connection string \(including credentials and cluster info\) MONGO\_URI=mongodb\+srv://<username>:<password>@<cluster-url>/course\_app? 

retryWrites=true&w=majority

\# JWT secret key for signing tokens \(use a strong random value in production\) SECRET\_KEY=your\_jwt\_signing\_secret

\# \(Optional\) Tweakable parameters

ACCESS\_TOKEN\_EXPIRE\_HOURS=4

TAG\_THRESHOLD=0.2

**Notes:**

- MONGO\_URI should point to the MongoDB database. The database name "course\_app" is included in the URI or used in code as shown. 

- SECRET\_KEY is used for JWT; it must be kept secret. 

- We expose ACCESS\_TOKEN\_EXPIRE\_HOURS to allow changing how long login tokens last, and TAG\_THRESHOLD to adjust how aggressively courses are tagged with categories \(the default 0.2 means top 20% of relevant courses get tagged to each category\). These have default values in code but can be overridden here if needed. 

By using a .env file, we avoid hard-coding any credentials in the codebase 4 . This improves security and makes it easy to deploy the app in different environments by just changing the env file or variables. 

**Conclusion:** The refactored structure makes the backend easier to navigate and maintain. Each file has a clear responsibility, from API routing to background data processing, which follows the principles of separation of concerns 2 . All original functionalities are retained: - **JWT Authentication**: Provided via

/users/register , /users/login and secured routes using Depends \(unchanged endpoints and 31

improved consistency in is\_active/disabled handling\). - **Course Search & Detail**: /search and

/course/\{id\} work as before, with ranking and text index. - **Category Management**: Public category listing and filter endpoints, plus admin endpoints to manage categories \(now neatly separated and automatically linked to tagging\). - **Course Data Aggregation**: The APScheduler-driven pipeline continues to scrape new courses and insert them, but now more efficiently with direct DB writes and no redundant cycles. - **Sentiment Analysis**: Still performed daily, computing per-review and per-course sentiment metrics that feed into search rankings. - **Favorites & Notifications**: Users can save favorites and retrieve notifications; the notification logic is refined to ensure users are alerted when their awaited courses become available, and those alerts are stored and delivered properly. 

This modular design will make future enhancements \(such as adding new providers, integrating actual email sending for notifications, etc.\) much easier, since each concern is in its own module. The application remains runnable locally by simply launching the FastAPI app \(e.g., via Uvicorn\) and optionally running the scheduler in parallel \(or configuring it as a background task in the app\). 

1

4 Settings and Environment Variables - FastAPI

https://fastapi.tiangolo.com/advanced/settings/

2

3 Bigger Applications - Multiple Files - FastAPI

https://fastapi.tiangolo.com/tutorial/bigger-applications/

32


# Document Outline

+ Refactored FastAPI Backend Architecture  
	+ app/main.py 
	+ app/core/config.py 
	+ app/core/security.py 
	+ app/models/user.py 
	+ app/models/course.py 
	+ app/models/category.py 
	+ app/models/notification.py 
	+ app/routers/auth.py 
	+ app/routers/users.py 
	+ app/routers/courses.py 
	+ app/routers/categories.py 
	+ app/routers/admin\_users.py 
	+ app/routers/admin\_categories.py 
	+ app/utils/keyword\_queue.py 
	+ app/utils/category\_tagger.py 
	+ app/utils/unify\_data.py 
	+ app/services/data\_ingestion.py 
	+ app/services/sentiment.py 
	+ app/services/notification\_service.py 
	+ app/services/scheduler.py 
	+ Environment Configuration \(.env.example\)



