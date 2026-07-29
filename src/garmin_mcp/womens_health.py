"""
Women's health functions for Garmin Connect MCP Server
"""
import datetime
import json
from typing import Any, Dict, List, Optional, Union

# The garmin_client will be set by the main file
garmin_client = None


def _to_json_str(data):
    """Convert data to JSON string if it's not already a string"""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)


def configure(client):
    """Configure the module with the Garmin client instance"""
    global garmin_client
    garmin_client = client


def register_tools(app):
    """Register all women's health tools with the MCP server app"""
    
    @app.tool()
    async def get_pregnancy_summary() -> str:
        """Get pregnancy summary data"""
        try:
            summary = garmin_client.get_pregnancy_summary()
            if not summary:
                return "No pregnancy summary data found."
            return _to_json_str(summary)
        except Exception as e:
            return f"Error retrieving pregnancy summary: {str(e)}"
    
    @app.tool()
    async def get_menstrual_data_for_date(date: str) -> str:
        """Get menstrual data for a specific date
        
        Args:
            date: Date in YYYY-MM-DD format
        """
        try:
            data = garmin_client.get_menstrual_data_for_date(date)
            if not data:
                return f"No menstrual data found for {date}."
            return _to_json_str(data)
        except Exception as e:
            return f"Error retrieving menstrual data: {str(e)}"
    
    @app.tool()
    async def get_menstrual_calendar_data(start_date: str, end_date: str) -> str:
        """Get menstrual calendar data between specified dates
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
        """
        try:
            data = garmin_client.get_menstrual_calendar_data(start_date, end_date)
            if not data:
                return f"No menstrual calendar data found between {start_date} and {end_date}."
            return _to_json_str(data)
        except Exception as e:
            return f"Error retrieving menstrual calendar data: {str(e)}"

    return app
