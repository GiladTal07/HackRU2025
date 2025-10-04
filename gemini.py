from google import genai
from google.genai import types
import pathlib
import os
from dotenv import load_dotenv
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Retrieve and encode the PDF byte
filepath = pathlib.Path('Resume.pdf')   
courses_path = pathlib.Path('rutgers_courses_2025_9_NB.json')
output_md = pathlib.Path('resume_recommendation.md')

prompt = """
You are an expert academic and career advisor.
Analyze the provided resume carefully and, using the attached Rutgers courses catalog (JSON), provide:
1. Course recommendations to strengthen the person’s skills.
2. Possible career paths based on their experience, strengths, and interests.
3. Key skills or technologies they should learn next.
4. A short summary of their profile in 3–4 sentences.
5. A future course plan: give a short-term (next 6–12 months) and long-term (1–3 years) recommended sequence of courses and learning milestones. When possible, reference specific Rutgers course codes/names from the attached JSON and explain why each course is recommended and what prerequisites or parallel learning (projects, tools) are suggested.

Respond in a well-structured markdown format, using headings for each numbered section and a clear short roadmap for the future course plan.
"""
if not os.getenv("GEMINI_API_KEY"):
    raise SystemExit("GEMINI_API_KEY not set in environment. Please add it to your .env or environment variables.")

if not filepath.exists():
    raise SystemExit(f"Resume file not found at {filepath.resolve()}")

if not courses_path.exists():
    raise SystemExit(f"Courses JSON file not found at {courses_path.resolve()}")

# Load courses JSON for local filtering
import json
import time
try:
    courses_data = json.loads(courses_path.read_text(encoding='utf-8'))
except Exception as e:
    raise SystemExit(f"Failed to read or parse courses JSON: {e}")

try:
    # Step 1: Ask model for a single-word major descriptor
    step1_prompt = (
        "You are an expert career/major predictor.\n"
        "Based only on the attached resume (PDF), return a SINGLE WORD that best describes the student's major (e.g., 'electrical', 'computer', 'anthropology').\n"
        "Return ONLY that single word in plaintext, no JSON and no extra text.\n"
    )

    step1 = client.models.generate_content(
      model="gemini-2.5-flash",
      contents=[
          types.Part.from_bytes(data=filepath.read_bytes(), mime_type='application/pdf'),
          step1_prompt,
      ])

    step1_text = getattr(step1, 'text', None) or str(step1)
    import re
    # Extract the first word token from the response
    m = re.search(r"[A-Za-z0-9_+-]+", step1_text)
    if m:
        predicted_one_word = m.group(0).strip()
    else:
        # fallback to scanning resume bytes for common keywords
        raw = filepath.read_bytes().decode('utf-8', errors='ignore').lower()
        for kw in ('electrical', 'ece', 'computer', 'anthropology', 'civil'):
            if kw in raw:
                predicted_one_word = kw
                break
        else:
            predicted_one_word = 'undecided'

    predicted_major_clean = predicted_one_word
    predicted_major_safe = re.sub(r"[^0-9a-zA-Z_-]", "_", predicted_major_clean)

    # courses_data may be a list or a dict with lists; attempt to get a list of course records
    if isinstance(courses_data, dict):
        lists = [v for v in courses_data.values() if isinstance(v, list)]
        possible = lists[0] if lists else []
    elif isinstance(courses_data, list):
        possible = courses_data
    else:
        possible = []

    # Filter by explicit 'major' field when present, else fall back to text match on title/description
    def matches_major_field(course, major):
        # check common keys
        for key in ('major', 'majors', 'department', 'subject'):
            val = course.get(key)
            if not val:
                continue
            if isinstance(val, list):
                vals = [str(x).lower() for x in val]
                if major.lower() in ' '.join(vals):
                    return True
            else:
                if major.lower() in str(val).lower():
                    return True
        return False

    def text_match(course, major):
        text = ' '.join([str(course.get(k, '')).lower() for k in ('title', 'description', 'name', 'catalog_description')])
        return major.lower() in text

    filtered = []
    for c in possible:
        if not isinstance(c, dict):
            continue
        if matches_major_field(c, predicted_major_clean):
            filtered.append(c)
        elif text_match(c, predicted_major_clean):
            filtered.append(c)

    # If filtering removed everything, fall back to a subset of possible
    if not filtered:
        filtered = possible[:100]

    # We will not write an intermediate filtered JSON (per request). Instead collect selected course dicts
    instructor_keys = {'instructor', 'instructors', 'faculty', 'professor', 'lecturer', 'course_instructor'}
    selected_courses = []

    # Also create a lightweight text file with course names (one per line) to reduce payload for step2
    names_path = pathlib.Path(f"rutgers_course_names_{predicted_major_safe}.txt")
    try:
        count = 0
        with names_path.open('w', encoding='utf-8') as fh:
            for c in possible:
                if not isinstance(c, dict):
                    continue
                # match the predicted single word against common fields
                combined = ' '.join([str(c.get(k, '')).lower() for k in ('major', 'majors', 'department', 'subject', 'title', 'name', 'description', 'catalog_description')])
                if predicted_major_clean.lower() in combined:
                    # remove instructor-like keys for privacy before saving selection
                    cleaned_course = {k: v for k, v in c.items() if k.lower() not in instructor_keys}
                    selected_courses.append(cleaned_course)
                    name = cleaned_course.get('title') or cleaned_course.get('name') or cleaned_course.get('course_title') or cleaned_course.get('course_code') or cleaned_course.get('code') or ''
                    if name:
                        fh.write(str(name).strip() + '\n')
                        count += 1
        print(f"Wrote lightweight course names to {names_path.resolve()} ({count} lines) — filtered by one-word major '{predicted_major_clean}'")
    except Exception as e:
        print(f"Warning: failed to write names file: {e}")

    # Step 2: Ask model for recommendations using reduced course set
    # Use the raw step1 text as the evidence snippet (step1 returned the one-word major)
    evidence_snippet = (step1_text or '')[:300]
    step2_prompt = (
        f"You are an expert academic and career advisor. The predicted major based on the resume is '{predicted_major_clean}'. Evidence: {evidence_snippet}\n"
        "Using the attached lightweight course name list (text) and the resume excerpt provided, do the following:\n"
        "1) Prioritize recommending courses that belong to the predicted major (at least 80% of recommendations). You may include up to two cross-discipline electives.\n"
        "2) Provide short-term (6–12 months) and long-term (1–3 years) course roadmaps, referencing Rutgers course codes/names when present.\n"
        "3) Provide career paths and key skills to learn.\n"
        "4) Provide a 3–4 sentence summary.\n"
        "Respond in well-structured markdown. Also include a small JSON at the end with keys: recommended_courses (array of course codes), short_term (array), long_term (array) for machine parsing.\n"
    )

    # Send resume + filtered courses JSON (as text) + prompt
    # Try sending the filtered course file; retry on transient server errors
    response = None
    last_exception = None
    for attempt in range(3):
        try:
            print(f"Step2 request attempt {attempt+1}/3 — sending names text file ({names_path.name}) and resume excerpt")
            # attach a small resume text excerpt (best-effort) to give the model direct evidence
            try:
                resume_text_excerpt = filepath.read_bytes().decode('utf-8', errors='ignore')[:5000]
            except Exception:
                resume_text_excerpt = ''

            contents = [
                types.Part.from_bytes(data=names_path.read_bytes(), mime_type='text/plain'),
            ]
            if resume_text_excerpt:
                contents.append(types.Part.from_bytes(data=resume_text_excerpt.encode('utf-8'), mime_type='text/plain'))
            contents.append(step2_prompt)

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
            )
            break
        except Exception as e:
            last_exception = e
            msg = str(e)
            print(f"Step2 attempt {attempt+1} failed: {msg}")
            # If internal server error, retry with exponential backoff
            if '500' in msg or 'INTERNAL' in msg.upper():
                backoff = 2 ** attempt
                print(f"Transient server error detected, retrying after {backoff}s...")
                time.sleep(backoff)
                continue
            else:
                # Non-transient error; break and handle below
                break

    if response is None:
        # Fallback: create a condensed textual summary of filtered courses and resend once
        print("Falling back to sending condensed course summary instead of full JSON.")
        try:
            # Build a short textual list: code - title: short description
            summary_lines = []
            for c in (selected_courses[:50] if isinstance(selected_courses, list) else []):
                code = c.get('course_code') or c.get('code') or c.get('subject') or ''
                title = c.get('title') or c.get('name') or ''
                desc = c.get('description') or c.get('catalog_description') or ''
                line = f"{code} - {title}: {desc}" if (code or title) else str(c)
                summary_lines.append(line)
            condensed = "\n".join(summary_lines)[:20000]

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=condensed.encode('utf-8'), mime_type='text/plain'),
                    step2_prompt,
                ])
        except Exception as e:
            raise SystemExit(f"Step2 failed after retries and fallback: {e}\nLast exception: {last_exception}")
    # Some client responses may have .text or nested fields; print safely and save to file
    text = getattr(response, 'text', None)
    if not text:
        text = str(response)

    print(text)
    # Remove any trailing JSON/fenced JSON block from the model response before saving
    try:
        cleaned_text = re.sub(r"```json[\s\S]*?```", "", text)
        cleaned_text = re.sub(r"\n?\{[\s\S]*\}\s*$", "", cleaned_text)
    except Exception:
        cleaned_text = text

    try:
        output_md.write_text(cleaned_text, encoding='utf-8')
        print(f"Saved recommendation to {output_md.resolve()}")
    except Exception as e:
        print(f"Failed to save output file: {e}")
    # --- New: extract recommended course names and match to course codes in the original JSON ---
    try:
        import difflib
        # 1) Try to extract trailing JSON block first
        recs = None
        json_match = None
        m = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if m:
            json_match = m.group(1)
        else:
            m2 = re.search(r"(\{[\s\S]*\})\s*$", text)
            if m2:
                json_match = m2.group(1)

        if json_match:
            try:
                parsed = json.loads(json_match)
                if isinstance(parsed, dict) and 'recommended_courses' in parsed:
                    recs = parsed.get('recommended_courses')
            except Exception:
                recs = None

        # 2) Fallback: extract lines under 'Recommended Courses' heading
        if not recs:
            m3 = re.search(r"###\s*Recommended Courses([\s\S]*?)(?:\n###|\n\n---|$)", text, re.IGNORECASE)
            if m3:
                block = m3.group(1)
                # capture bullets or numbered lists
                lines = [ln.strip(' *\t') for ln in block.splitlines() if ln.strip()]
                # filter out short lines
                recs = []
                for ln in lines:
                    # remove leading numbering
                    ln2 = re.sub(r"^\d+\.\s*", '', ln)
                    # take up to line content before a dash
                    ln2 = ln2.split(' - ')[0].strip()
                    if ln2:
                        recs.append(ln2)

        if not recs:
            print("No recommended courses list found in model response; skipping code matching.")
        else:
            # Normalize courses_data to a list of dicts
            if isinstance(courses_data, dict):
                lists = [v for v in courses_data.values() if isinstance(v, list)]
                candidates = lists[0] if lists else []
            elif isinstance(courses_data, list):
                candidates = courses_data
            else:
                candidates = []

            # Build simple lookup lists
            candidate_titles = []
            title_to_course = {}
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                title = (c.get('title') or c.get('name') or c.get('course_title') or '')
                code = (c.get('course_code') or c.get('code') or c.get('subject') or '')
                key = (title or code).strip()
                if key:
                    candidate_titles.append(key)
                    title_to_course[key] = c

            matched = []
            for rec in recs:
                found = None
                rec_low = rec.lower()
                # exact code match
                for key, course in title_to_course.items():
                    if key.lower() == rec_low:
                        found = course
                        break
                # substring title match
                if not found:
                    for key, course in title_to_course.items():
                        if rec_low in key.lower() or key.lower() in rec_low:
                            found = course
                            break
                # fuzzy match
                if not found and candidate_titles:
                    best = difflib.get_close_matches(rec, candidate_titles, n=1, cutoff=0.6)
                    if best:
                        found = title_to_course.get(best[0])

                matched_code = None
                matched_title = None
                if found:
                    matched_code = (found.get('course_code') or found.get('code') or found.get('subject') or '')
                    matched_title = (found.get('title') or found.get('name') or '')
                matched.append({'recommended': rec, 'matched_code': matched_code, 'matched_title': matched_title})

            # Do not write a mapping JSON file or a separate with_codes markdown (user requested no last JSON)
            # Keep matched list in-memory for inline processing below
            print(f"Matched {len(matched)} recommended courses (mapping not written to disk per user preference)")
    except Exception as e:
        print(f"Failed to extract/match recommended courses: {e}")
    # Ensure mapping variable exists for downstream inline steps
    mapping = matched if 'matched' in locals() else []
    # --- New: create an inline-coded markdown where course lines contain matched codes ---
    try:
        # use in-memory mapping from the previous step
        mapping = matched if 'matched' in locals() else []
        rec_to_code = {m['recommended']: (m['matched_code'] or '').strip() for m in mapping}
        md_text = output_md.read_text(encoding='utf-8')
        # Replace lines under '### Recommended Courses' with inline codes where possible
        def replace_block(match):
            block = match.group(1)
            lines = [ln for ln in block.splitlines() if ln.strip()]
            out_lines = []
            for ln in lines:
                ln_clean = re.sub(r"^\s*[-*\d\.\)]+\s*", '', ln).strip()
                code = rec_to_code.get(ln_clean)
                if code:
                    out_lines.append(f"- {ln_clean} ({code})")
                else:
                    out_lines.append(f"- {ln_clean}")
            return '\n'.join(out_lines)

        md_new = re.sub(r"###\s*Recommended Courses([\s\S]*?)(?:\n###|\n\n---|$)", lambda m: "### Recommended Courses\n\n" + replace_block(m) + "\n\n", md_text, flags=re.IGNORECASE)
        inline_file = output_md.with_name(output_md.stem + '_inline_codes' + output_md.suffix)
        inline_file.write_text(md_new, encoding='utf-8')
        print(f"Wrote inline-coded recommendation to {inline_file.resolve()}")
    except Exception as e:
        print(f"Failed to create inline-coded markdown: {e}")
    # Second-pass: more robust line-by-line replacement (v2)
    try:
        # Always attempt v2 inline insertion. If `mapping` is empty, build a fallback mapping
        # by extracting the Recommended Courses block from the saved markdown and fuzzy-matching
        # each line against the local courses_data.
        lines = md_text.splitlines()

        if not mapping:
            import difflib
            # Normalize courses_data to list of candidates
            if isinstance(courses_data, dict):
                lists = [v for v in courses_data.values() if isinstance(v, list)]
                candidates = lists[0] if lists else []
            elif isinstance(courses_data, list):
                candidates = courses_data
            else:
                candidates = []

            candidate_titles = []
            title_to_course = {}
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                title = (c.get('title') or c.get('name') or c.get('course_title') or '')
                code = (c.get('course_code') or c.get('code') or c.get('subject') or '')
                key = (title or code).strip()
                if key:
                    candidate_titles.append(key)
                    title_to_course[key] = c

            # locate Recommended Courses block indices
            start_idx = None
            end_idx = None
            for i, ln in enumerate(lines):
                if re.match(r"^###\s*Recommended Courses", ln, flags=re.IGNORECASE):
                    start_idx = i
                    break
            if start_idx is not None:
                for j in range(start_idx+1, len(lines)):
                    if re.match(r"^###\s", lines[j]):
                        end_idx = j
                        break
                if end_idx is None:
                    for j in range(start_idx+1, len(lines)):
                        if lines[j].strip().startswith('---'):
                            end_idx = j
                            break
                if end_idx is None:
                    end_idx = len(lines)

                # extract recommendation lines and fuzzy-match to build mapping
                rec_lines = []
                for k in range(start_idx+1, end_idx):
                    ln = lines[k].strip()
                    if not ln:
                        continue
                    ln_clean = re.sub(r"^\s*[-*\d\.\)]+\s*", '', ln).strip()
                    if ln_clean:
                        rec_lines.append(ln_clean)

                new_mapping = []
                for rec in rec_lines:
                    found = None
                    rec_low = rec.lower()
                    # exact match
                    for key in title_to_course:
                        if key.lower() == rec_low:
                            found = title_to_course[key]
                            break
                    # substring
                    if not found:
                        for key in title_to_course:
                            if rec_low in key.lower() or key.lower() in rec_low:
                                found = title_to_course[key]
                                break
                    # fuzzy
                    if not found and candidate_titles:
                        best = difflib.get_close_matches(rec, candidate_titles, n=1, cutoff=0.6)
                        if best:
                            found = title_to_course.get(best[0])

                    matched_code = ''
                    matched_title = ''
                    if found:
                        matched_code = (found.get('course_code') or found.get('code') or found.get('subject') or '')
                        matched_title = (found.get('title') or found.get('name') or '')
                    new_mapping.append({'recommended': rec, 'matched_code': matched_code, 'matched_title': matched_title})

                mapping = new_mapping

        # Now perform line replacements using `mapping` (whether original or fallback)
        # find Recommended Courses indices (recompute to be safe)
        start_idx = None
        end_idx = None
        for i, ln in enumerate(lines):
            if re.match(r"^###\s*Recommended Courses", ln, flags=re.IGNORECASE):
                start_idx = i
                break
        if start_idx is not None:
            for j in range(start_idx+1, len(lines)):
                if re.match(r"^###\s", lines[j]):
                    end_idx = j
                    break
            if end_idx is None:
                for j in range(start_idx+1, len(lines)):
                    if lines[j].strip().startswith('---'):
                        end_idx = j
                        break
            if end_idx is None:
                end_idx = len(lines)

            for k in range(start_idx+1, end_idx):
                line = lines[k]
                # only modify bullet or numbered lines
                if not re.search(r"^\s*([*\-]|\d+\.)", line):
                    continue
                for m in mapping:
                    rec = m.get('recommended', '')
                    code = (m.get('matched_code') or '').strip()
                    if not rec or not code:
                        continue
                    if rec.lower() in line.lower():
                        if code not in line:
                            lines[k] = line.rstrip() + f" ({code})"
                        break

        md_v2 = '\n'.join(lines)
        inline_v2 = output_md.with_name(output_md.stem + '_inline_codes_v2' + output_md.suffix)
        inline_v2.write_text(md_v2, encoding='utf-8')
        print(f"Wrote robust inline-coded recommendation to {inline_v2.resolve()}")
    except Exception as e:
        print(f"Failed to create v2 inline-coded markdown: {e}")
except Exception as e:
    raise SystemExit(f"Request failed: {e}")
