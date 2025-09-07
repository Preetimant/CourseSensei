# CourseSensei — Smart AI chatbot for Course Inquiries

CourseSensei is an ontology-driven NLP chatbot that answers course-related queries (course overview, instructors, assessments, session plans, contact details, etc.) by extracting structured information from course outline documents (PDF & DOCX), converting them into JSON, generating an OWL ontology and Dialogflow intents, and serving dynamic answers via a Flask webhook that queries the ontology. Developed as part of Capstone Project 2025.

---

## Key features

* **Automated data ingestion** — Extracts tabular and textual sections from course PDFs/DOCX (metadata, instructor details, assessment tables, session plans) and stores them as structured JSON.
* **OWL ontology generation** — Converts JSON course records into a machine‑readable ontology (OWL) modeling Programs, Terms, Courses, Sessions, Assessments, and Instructors.
* **Ontology-backed webhook** — A Flask webhook loads the OWL file using `owlready2`, answers queries by traversing object/data properties, supports pagination and cached lookups.
* **Dialogflow intent generation** — Produces Dialogflow intent JSONs + entity files automatically (training phrases, parameter mapping) for \~30 course-related queries.
* **Easy deployment workflow** — Extract information → Generate JSON → Build Ontology → Expose Flask Webhook (ngrok) → Wire Dialogflow webhook → Generate Intents → Import into Dialogflow Agent.

---

## Requirements

* Python 3.8+ (recommended)
* Primary Python packages used in the codebase:

  ```bash
  pip install owlready2 flask flask-cors python-docx pdfplumber
  ```

  (Other stdlib modules: `os`, `json`, `uuid`, `shutil`, `re`, `logging`, `functools`, `collections`, `datetime`.)

---

## How it works — pipeline (short)

1. **Extract** — Run the extraction script `extractor+owl.ipynb` to crawl `inputs/`, read each PDF/DOCX and create a normalized JSON per course containing `course_metadata`, `basic_info`, `instructor_details`, `assessment`, `session_plan`.

2. **Generate OWL** — The script `extractor+owl.ipynb` also converts the JSON collection into an OWL ontology (`university_courses.owl`). This script defines classes like `Program`, `Term`, `Course`, `Assessment`, `SessionPlan` and sets up object/data properties used by the webhook.

3.**Run webhook** — Start `webhook.py` (a Flask app). The webhook loads `university_courses.owl`, accepts Dialogflow webhook requests, runs query handlers (instructor lookup, assessment percentage, session details, etc.) and returns `fulfillmentText` responses. Expose the webhook using `ngrok` for Dialogflow to reach it. 

4. **Create Dialogflow agent** — Run `intent-generation.ipynb` to create Dialogflow intent files and entity files in a `dialogflow_agent/` folder, then package them into a zip that should be imported in Dialogflow. The generator creates \~30 intents (examples in `querieslist.docx`) and wires each intent to call the webhook for answers.

5. **Import & test** — Import the generated Dialogflow agent zip in Dialogflow console, set the webhook URL to your ngrok forwarding URL + `/webhook`, and test queries (sample queries are in `querieslist.docx`).

---

## Quickstart (example commands)

**Run the extractor + OWL generator (Jupyter or Colab)**

1. Place raw course PDFs/DOCX into `inputs/`:

2. Open `extractor+owl.ipynb` and run the cells in order (edit the top path variables if your folders differ).

**Run the webhook**

```bash
python webhook.py
```

**Expose it with ngrok**

```bash
ngrok http 5000
```

Copy the generated forwarding URL and paste into the URL field of "create_metadata" function of intent-generation.ipynb as `<ngrok-url>/webhook`.

**Generate Dialogflow Intents**

1. Update the URL field in "create_metadata" (update required only once in case you have a static ngrok url else required everytime webhook is rerun).
2. Run `intent-generation.ipynb`(edit path in main function if required).
3. Upload generated zip to Dialogflow.
---

## Known issues & notes

* Course outline documents are inconsistent (file naming, merged/continued table rows, varying header names). The project includes heuristics to handle these, but some manual cleaning may still be required for edge cases.
* The intent generator assumes Dialogflow V2 agent structure and uses the webhook for most answers — small edits to `agent.json` may be necessary depending on your Dialogflow account/region.
* Scripts have hardcoded default paths (e.g. Google Drive paths). Edit the bottom `__main__` section of the scripts to set `input_folder` and `output_folder` before running in your environment.

---

## Troubleshooting

* If the webhook returns errors, ensure `university_courses.owl` is present and accessible to the Flask process.
* If some answers are missing, check the generated JSONs for missing/`NA` fields (extraction heuristics may have skipped malformed tables).
* To add more training phrases or more robust entity synonyms, update the entity JSONs in `dialogflow_agent/entities/` before importing.

---

## License

This project is **proprietary**. All rights reserved.

Copyright (c) 2025 Preetimant Bora Bhowal. All rights reserved.

No part of this codebase may be used, reproduced, distributed, modified, or sublicensed in any form without prior written permission from the copyright holder. For licensing requests or permission to use the code, please contact: `preetimant.official@gmail.com`.
