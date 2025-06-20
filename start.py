#!/usr/bin/env python3
"""
Convenience script to start the Course Discovery API
"""

import os
import sys
import subprocess

def main():
    print("🚀 Starting Course Discovery API...")
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("⚠️  Warning: .env file not found!")
        print("📋 Please create a .env file with the following variables:")
        print("   MONGO_URI=mongodb://your-connection-string")
        print("   SECRET_KEY=your-secret-key")
        print("\n💡 You can copy env.example to .env and modify it")
        
        # Ask if user wants to continue with default values
        response = input("\nContinue with test values? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
        
        # Set default test values
        os.environ['MONGO_URI'] = 'mongodb://localhost:27017/course_app_dev'
        os.environ['SECRET_KEY'] = 'development-secret-key-change-in-production'
        print("🔧 Using default development settings")
    
    try:
        print("🌐 Starting FastAPI server...")
        print("📖 API Documentation will be available at: http://localhost:8000/docs")
        print("🔍 Alternative docs at: http://localhost:8000/redoc")
        print("💚 Health check at: http://localhost:8000/health")
        print("\n📝 Press Ctrl+C to stop the server\n")
        
        # Start the FastAPI server
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--reload", 
            "--host", "0.0.0.0", 
            "--port", "8000"
        ])
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 