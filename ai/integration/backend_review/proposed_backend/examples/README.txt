SYNTHETIC INTEGRATION FIXTURES, NOT REAL ASTRONAUT DATA

Nine consecutive daily observations: seven calibration records followed by two prediction requests. Derived only from training participant SIM_001 in the original simulator audit table; renamed DEMO_SIM_001 for local integration isolation. These examples verify the HTTP/history contract, not model accuracy. No targets or baselines are accepted from the frontend.

POST synthetic_daily_sequence.json entries one at a time to /api/v1/assess on a fresh demo database. First seven should collect calibration; entries eight and nine can call the model when AI_SERVICE_URL is configured. Dates are historical simulation cutoffs so the demo does not require waiting seven actual days. Never pass this fixture as measured human history.

assess_request_day8.json is the frontend request. expected_model_request_day8.json is the backend-derived 22-field model request, calculated using the existing Python feature helper.
