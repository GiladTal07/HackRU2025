import requests
import json

def save_full_course_info(year=2025, term=9, campus="NB", filename=None):
    """Fetch Rutgers course info and save major name, full code, title, and instructors."""
    url = "https://classes.rutgers.edu/soc/api/courses.json"
    params = {"year": year, "term": term, "campus": campus}
    
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()

        courses = []
        for c in data:
            major_name = c.get("subjectDescription", "Unknown Major")
            full_code = c.get("courseString", "N/A")  # e.g. "01:198:111"
            course_title = c.get("title", "Untitled Course")
            
            # Collect instructor names from all sections
            instructors = set()
            for section in c.get("sections", []):
                for prof in section.get("instructors", []):
                    instructors.add(prof.get("name", "Unknown Instructor"))
            
            courses.append({
                "major": major_name,
                "course_code": full_code,
                "course_title": course_title,
                "instructors": list(instructors)
            })

        filename = filename or f"rutgers_courses_{year}_{term}_{campus}.json"
        if not filename.endswith(".json"):
            filename += ".json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(courses, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved {len(courses)} courses to {filename}")
    
    except requests.RequestException as err:
        print("❌ Network error:", err)
    except Exception as e:
        print("❌ Error saving data:", e)


if __name__ == "__main__":
    save_full_course_info()
