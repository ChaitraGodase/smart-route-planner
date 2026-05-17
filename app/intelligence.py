import math

class EnvironmentalAI:
    @staticmethod
    def get_weather_risk(weather_data: dict) -> float:
        risk = 0.0
        if weather_data.get('rain_mm', 0) > 5: risk += 0.2
        if weather_data.get('snow_cm', 0) > 0: risk += 0.5
        if weather_data.get('visibility_m', 1000) < 200: risk += 0.3
        return min(risk, 1.0)

    @staticmethod
    def get_terrain_risk(slopes: list, vehicle_type: str) -> dict:
        max_slope = max(slopes) if slopes else 0
        min_slope = min(slopes) if slopes else 0
        
        limits = {
            'car': {'max_up': 15, 'max_down': -15},
            'bike': {'max_up': 10, 'max_down': -10},
            'foot': {'max_up': 25, 'max_down': -25}
        }
        
        limits = limits.get(vehicle_type, limits['car'])
        risk = 0.0
        
        if max_slope > limits['max_up']: risk += 0.4
        if min_slope < limits['max_down']: risk += 0.5
            
        return {
            "risk_score": min(risk, 1.0),
            "max_incline": round(max_slope, 2),
            "max_decline": round(min_slope, 2),
            "is_safe": risk < 0.3
        }

    @staticmethod
    def generate_weather_mock() -> dict:
        return {"temp_c": 15, "rain_mm": 2.5, "snow_cm": 0, "visibility_m": 800, "wind_kmh": 20}
