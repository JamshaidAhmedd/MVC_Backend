from fastapi import FastAPI
from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.courses import router as courses_router
from routers.categories import router as categories_router
from routers.admin_users import router as admin_users_router
from routers.admin_categories import router as admin_categories_router

app = FastAPI(
    title="Course Discovery API",
    version="2.0",
    description="A backend for course aggregation, search, categories, user profiles, favorites, and notifications"
)

# Include routers for different API sections
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(courses_router)
app.include_router(categories_router)
app.include_router(admin_users_router)
app.include_router(admin_categories_router)

# Health check endpoint
@app.get("/")
def read_root():
    return {"message": "Course Discovery API is running", "version": "2.0"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
