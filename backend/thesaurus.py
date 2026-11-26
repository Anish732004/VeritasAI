"""Built-in research thesaurus for the rule-based concept map (no AI, no network).

Each entry maps a phrase (lower case, as it appears in a question) to a label and the
alternative terms a paper's title or abstract might use. Keep entries general: a concept
belongs here when researchers commonly write it in more than one way. Add new topics
freely; tests/test_concepts.py checks the structure and tests/data/ holds the benchmarks
used to measure whether a change helps.
"""

# phrase -> (label, terms). Multi-word phrases are kept together when they appear in a question.
SYNONYMS: dict[str, tuple[str, list[str]]] = {
    # --- computing and AI
    "ai": ("Artificial intelligence", ["artificial intelligence", "AI", "machine learning", "deep learning"]),
    "artificial intelligence": ("Artificial intelligence", ["artificial intelligence", "AI", "machine learning", "deep learning"]),
    "machine learning": ("Machine learning", ["machine learning", "deep learning", "neural network", "random forest", "gradient boosting"]),
    "deep learning": ("Deep learning", ["deep learning", "neural network", "LSTM", "convolutional neural network"]),
    "generative ai": ("Generative AI", ["generative AI", "large language model", "ChatGPT", "LLM"]),
    "large language model": ("Large language models", ["large language model", "large language models", "LLM", "ChatGPT", "GPT-4", "generative AI"]),
    "large language models": ("Large language models", ["large language model", "large language models", "LLM", "ChatGPT", "GPT-4", "generative AI"]),
    "natural language processing": ("Natural language processing", ["natural language processing", "NLP", "text mining", "text classification"]),
    "computer vision": ("Computer vision", ["computer vision", "image recognition", "object detection", "image classification"]),
    "chatbot": ("Chatbots", ["chatbot", "conversational agent", "virtual assistant"]),
    "internet of things": ("Internet of Things", ["Internet of Things", "IoT", "smart devices", "connected devices", "sensor networks"]),
    "blockchain": ("Blockchain", ["blockchain", "distributed ledger", "distributed ledger technology", "smart contracts"]),
    "cybersecurity": ("Cybersecurity", ["cybersecurity", "cyber security", "information security", "cyber attack", "cyberattack"]),
    "big data": ("Big data", ["big data", "big data analytics", "data analytics"]),
    "digital transformation": ("Digital transformation", ["digital transformation", "digitalization", "digitalisation", "digital technologies"]),
    "automation": ("Automation", ["automation", "robotic process automation", "robotics", "automated"]),
    "augmented reality": ("Augmented reality", ["augmented reality", "AR", "mixed reality"]),
    "virtual reality": ("Virtual reality", ["virtual reality", "VR", "immersive technology", "metaverse"]),
    "deepfake": ("Deepfakes", ["deepfake", "deepfakes", "synthetic media", "face manipulation", "manipulated video"]),
    "deepfakes": ("Deepfakes", ["deepfake", "deepfakes", "synthetic media", "face manipulation", "manipulated video"]),
    "misinformation": ("Misinformation", ["misinformation", "disinformation", "fake news"]),
    "fake news": ("Misinformation", ["fake news", "misinformation", "disinformation"]),
    "recommendation": ("Recommendations", ["recommender system", "recommendation system", "personalized recommendation"]),
    "algorithmic bias": ("Algorithmic bias", ["algorithmic bias", "algorithmic fairness", "AI bias", "discrimination"]),
    "grading": ("Grading and assessment", ["grading", "automated essay scoring", "automated assessment", "automated grading", "marking", "assessment"]),

    # --- energy and environment
    "energy": ("Energy", ["energy", "electricity", "power system"]),
    "energy sector": ("Energy", ["energy sector", "power sector", "electricity sector", "energy industry", "energy"]),
    "electricity": ("Electricity", ["electricity", "power system", "electric power"]),
    "electricity generation": ("Electricity generation", ["electricity generation", "power generation", "electric power generation", "power plant"]),
    "power generation": ("Electricity generation", ["power generation", "electricity generation", "electric power generation", "power plant"]),
    "renewable energy": ("Renewable energy", ["renewable energy", "solar", "wind power", "photovoltaic", "clean energy"]),
    "solar energy": ("Solar energy", ["solar energy", "solar power", "photovoltaic", "PV"]),
    "smart grid": ("Smart grid", ["smart grid", "power grid", "grid management", "demand response"]),
    "load forecasting": ("Load forecasting", ["load forecasting", "demand forecasting", "electricity demand prediction"]),
    "energy efficiency": ("Energy efficiency", ["energy efficiency", "energy saving", "energy consumption"]),
    "electric vehicle": ("Electric vehicles", ["electric vehicle", "electric vehicles", "EV", "battery electric vehicle"]),
    "electric vehicles": ("Electric vehicles", ["electric vehicle", "electric vehicles", "EV", "battery electric vehicle"]),
    "climate change": ("Climate change", ["climate change", "global warming"]),
    "sustainability": ("Sustainability", ["sustainability", "sustainable development", "sustainable"]),
    "circular economy": ("Circular economy", ["circular economy", "recycling", "reuse", "remanufacturing"]),
    "pro-environmental behaviour": ("Pro-environmental behaviour", ["pro-environmental behaviour", "pro-environmental behavior", "environmental behaviour", "green behaviour", "eco-friendly behaviour"]),
    "pro-environmental behavior": ("Pro-environmental behaviour", ["pro-environmental behaviour", "pro-environmental behavior", "environmental behaviour", "green behaviour", "eco-friendly behaviour"]),

    # --- manufacturing and operations
    "predictive maintenance": ("Predictive maintenance", ["predictive maintenance", "fault detection", "condition monitoring"]),
    "supply chain": ("Supply chain", ["supply chain", "logistics", "supply network"]),
    "transparency": ("Transparency", ["transparency", "traceability", "visibility", "disclosure"]),

    # --- business, finance and economics
    "personalisation": ("Personalisation", ["personalization", "personalisation", "personalized recommendation", "recommender system"]),
    "personalization": ("Personalisation", ["personalization", "personalisation", "personalized recommendation", "recommender system"]),
    "customer experience": ("Customer experience", ["customer experience", "customer satisfaction", "user experience"]),
    "customer satisfaction": ("Customer satisfaction", ["customer satisfaction", "customer experience"]),
    "customer retention": ("Customer retention", ["customer retention", "customer loyalty", "churn", "repurchase intention"]),
    "customer loyalty": ("Customer loyalty", ["customer loyalty", "customer retention", "repurchase intention"]),
    "ecommerce": ("E-commerce", ["e-commerce", "ecommerce", "online retail", "online shopping"]),
    "e-commerce": ("E-commerce", ["e-commerce", "ecommerce", "online retail", "online shopping"]),
    "online shopping": ("E-commerce", ["e-commerce", "online retail", "online shopping"]),
    "retail": ("Retail", ["retail", "retailing", "online retail"]),
    "liquidity risk": ("Liquidity risk", ["liquidity risk", "funding liquidity", "liquidity stress", "liquidity coverage ratio", "bank run", "deposit outflow"]),
    "credit risk": ("Credit risk", ["credit risk", "default prediction", "credit scoring", "loan default"]),
    "bank": ("Banking", ["bank", "banking", "financial institution"]),
    "banks": ("Banking", ["bank", "banking", "financial institution"]),
    "banking": ("Banking", ["bank", "banking", "financial institution"]),
    "fintech": ("Fintech", ["fintech", "financial technology", "digital finance", "mobile money"]),
    "financial inclusion": ("Financial inclusion", ["financial inclusion", "access to finance", "unbanked", "financial access"]),
    "microfinance": ("Microfinance", ["microfinance", "microcredit", "microloans", "group lending", "microfinance institutions"]),
    "poverty": ("Poverty", ["poverty", "poverty reduction", "poverty alleviation", "low income"]),
    "firm value": ("Firm value", ["firm value", "Tobin's Q", "market value", "firm performance"]),
    "firm performance": ("Firm performance", ["firm performance", "financial performance", "return on assets", "profitability"]),
    "corporate governance": ("Corporate governance", ["corporate governance", "board composition", "board independence", "ownership structure"]),
    "investment decisions": ("Investment decisions", ["investment decisions", "corporate investment", "capital expenditure", "investment efficiency"]),
    "overconfidence": ("Overconfidence", ["overconfidence", "managerial overconfidence", "CEO overconfidence", "hubris"]),
    "minimum wage": ("Minimum wage", ["minimum wage", "minimum wages", "wage floor"]),
    "youth employment": ("Youth employment", ["youth employment", "youth unemployment", "young workers", "teen employment"]),
    "unemployment": ("Unemployment", ["unemployment", "joblessness", "job loss"]),
    "entrepreneurship": ("Entrepreneurship", ["entrepreneurship", "entrepreneurs", "new ventures", "start-ups", "startups"]),

    # --- work and organisations
    "remote work": ("Remote work", ["remote work", "telework", "work from home", "hybrid work"]),
    "productivity": ("Productivity", ["productivity", "employee productivity", "work performance", "job performance"]),
    "employee productivity": ("Productivity", ["employee productivity", "productivity", "work performance", "job performance"]),
    "job satisfaction": ("Job satisfaction", ["job satisfaction", "employee satisfaction", "work satisfaction"]),
    "burnout": ("Burnout", ["burnout", "emotional exhaustion", "work stress"]),
    "green hrm": ("Green HRM", ["green HRM", "green human resource management", "GHRM", "green HR practices"]),

    # --- health
    "healthcare": ("Healthcare", ["healthcare", "health care", "hospital", "clinical"]),
    "telemedicine": ("Telemedicine", ["telemedicine", "telehealth", "telecare", "virtual consultation", "remote consultation"]),
    "telehealth": ("Telemedicine", ["telehealth", "telemedicine", "telecare", "virtual consultation", "remote consultation"]),
    "patient outcomes": ("Patient outcomes", ["patient outcomes", "clinical outcomes", "health outcomes"]),
    "mental health": ("Mental health", ["mental health", "depression", "anxiety", "well-being"]),
    "depression": ("Depression", ["depression", "depressive symptoms", "major depressive disorder"]),
    "anxiety": ("Anxiety", ["anxiety", "anxiety disorder", "anxiety symptoms"]),
    "well-being": ("Well-being", ["well-being", "wellbeing", "wellness", "life satisfaction"]),
    "wellbeing": ("Well-being", ["well-being", "wellbeing", "wellness", "life satisfaction"]),
    "covid-19": ("COVID-19", ["COVID-19", "SARS-CoV-2", "coronavirus", "pandemic"]),
    "physical activity": ("Physical activity", ["physical activity", "exercise", "sedentary behaviour"]),
    "obesity": ("Obesity", ["obesity", "overweight", "body mass index"]),

    # --- education
    "higher education": ("Higher education", ["higher education", "university", "students"]),
    "online learning": ("Online learning", ["online learning", "e-learning", "distance learning", "remote learning", "MOOC"]),
    "gamification": ("Gamification", ["gamification", "game-based learning", "serious games", "game elements"]),
    "student engagement": ("Student engagement", ["student engagement", "learner engagement", "academic engagement"]),
    "academic performance": ("Academic performance", ["academic performance", "academic achievement", "student achievement", "grades"]),
    "student essays": ("Student essays", ["student essays", "essays", "student writing", "essay writing"]),

    # --- society and media
    "social media": ("Social media", ["social media", "Instagram", "TikTok", "Facebook"]),
    "news media": ("News media", ["news media", "news", "journalism", "news outlets"]),
    "privacy": ("Privacy", ["privacy", "data protection", "privacy concern"]),
    "trust": ("Trust", ["trust", "consumer trust", "public trust", "credibility"]),
    "climate policy": ("Climate policy", ["climate policy", "environmental policy", "carbon policy"]),

    # --- populations and settings
    "students": ("Students", ["students", "higher education", "university students"]),
    "adolescents": ("Adolescents", ["adolescents", "adolescent", "teenagers", "youth", "young people"]),
    "older adults": ("Older adults", ["older adults", "elderly", "older people", "aged"]),
    "women": ("Women", ["women", "female", "gender"]),
    "employees": ("Employees", ["employees", "employee", "workers", "staff"]),
    "employee": ("Employees", ["employees", "employee", "workers", "staff"]),
    "developing countries": ("Developing countries", ["developing countries", "developing economies", "low-income countries", "emerging economies", "LMICs"]),
    "rural": ("Rural areas", ["rural", "rural areas", "rural communities"]),
    "rural areas": ("Rural areas", ["rural areas", "rural", "rural communities"]),
    "india": ("India", ["India", "Indian"]),
}

# Words that name a concept on their own and are often the head of a longer phrase:
# "electric vehicle adoption" is about electric vehicles AND adoption.
HEAD_CONCEPTS: dict[str, tuple[str, list[str]]] = {
    "adoption": ("Adoption", ["adoption", "uptake", "acceptance", "adoption intention"]),
}

# Phrases about a setting or population. They become optional once the question has two topics.
SETTING_WORDS = {"manufacturing", "agriculture", "transport", "transportation", "construction", "bank", "banks", "banking",
                 "ecommerce", "e-commerce", "retail", "online shopping", "healthcare", "hospital", "hospitals",
                 "higher education", "university", "universities", "school", "schools", "students", "smes", "sme", "firms",
                 "companies", "organisations", "organizations", "india", "uk", "china", "europe", "united states", "usa",
                 "developing countries", "employees", "employee", "adolescents", "older adults", "women", "rural",
                 "rural areas", "workers", "patients", "employee", "worker", "student", "patient", "consumer", "consumers",
                 "adolescent", "child", "children", "teenagers", "teens", "youth", "young people", "elderly", "older people",
                 "nurses", "teachers", "parents", "farmers", "smallholder farmers", "physicians", "doctors", "migrants",
                 "refugees", "smes", "small businesses"} | {
    # places: where a study is set, not what it is about
    "us", "u.s.", "america", "north america", "latin america", "south america", "africa", "sub-saharan africa", "asia",
    "southeast asia", "south asia", "east asia", "middle east", "gulf", "gcc", "eu", "european union", "oecd", "global south",
    "uae", "saudi arabia", "qatar", "oman", "kuwait", "bahrain", "egypt", "nigeria", "kenya", "ghana", "ethiopia", "south africa",
    "pakistan", "bangladesh", "sri lanka", "nepal", "indonesia", "malaysia", "singapore", "vietnam", "thailand", "philippines",
    "japan", "korea", "south korea", "taiwan", "australia", "new zealand", "canada", "mexico", "brazil", "argentina", "chile",
    "germany", "france", "italy", "spain", "netherlands", "sweden", "norway", "turkey", "russia", "iran", "england", "scotland"}

# Population words that start a longer phrase: "employee pro-environmental behaviour" is about
# employees (a setting) and pro-environmental behaviour (the topic).
POPULATION_PREFIX = {"employee", "employees", "worker", "workers", "student", "students", "patient", "patients",
                     "consumer", "consumers", "adolescent", "adolescents", "women", "older", "child", "children"}

# Heads whose modifier is the real topic: "mindfulness training" is about mindfulness, "chatbot
# technology" about chatbots. The modifier is searched as well as the whole phrase.
INSTRUMENT_HEADS = {"training", "programme", "programmes", "program", "programs", "intervention", "interventions",
                    "technology", "technologies", "system", "systems", "tool", "tools", "app", "apps", "application",
                    "applications", "platform", "platforms", "device", "devices", "initiative", "initiatives"}

# Standard acronyms: canonical spelling and expansion. Both forms are searched.
ACRONYMS: dict[str, tuple[str, str]] = {
    "ai": ("AI", "artificial intelligence"), "ml": ("ML", "machine learning"), "dl": ("DL", "deep learning"),
    "nlp": ("NLP", "natural language processing"), "llm": ("LLM", "large language model"),
    "llms": ("LLMs", "large language models"), "iot": ("IoT", "internet of things"), "gan": ("GAN", "generative adversarial network"),
    "cnn": ("CNN", "convolutional neural network"), "rnn": ("RNN", "recurrent neural network"), "lstm": ("LSTM", "long short-term memory"),
    "ar": ("AR", "augmented reality"), "vr": ("VR", "virtual reality"), "ux": ("UX", "user experience"),
    "ict": ("ICT", "information and communication technology"), "erp": ("ERP", "enterprise resource planning"),
    "crm": ("CRM", "customer relationship management"), "scm": ("SCM", "supply chain management"),
    "esg": ("ESG", "environmental social and governance"), "hrm": ("HRM", "human resource management"),
    "hr": ("HR", "human resources"), "ceo": ("CEO", "chief executive officer"), "cfo": ("CFO", "chief financial officer"),
    "roi": ("ROI", "return on investment"), "kpi": ("KPI", "key performance indicator"), "gdp": ("GDP", "gross domestic product"),
    "ev": ("EV", "electric vehicle"), "evs": ("EVs", "electric vehicles"), "pv": ("PV", "photovoltaic"),
    "ehr": ("EHR", "electronic health record"), "emr": ("EMR", "electronic medical record"), "icu": ("ICU", "intensive care unit"),
    "ptsd": ("PTSD", "post-traumatic stress disorder"), "adhd": ("ADHD", "attention deficit hyperactivity disorder"),
    "sdg": ("SDG", "sustainable development goals"), "sdgs": ("SDGs", "sustainable development goals"),
    "mooc": ("MOOC", "massive open online course"), "moocs": ("MOOCs", "massive open online courses"),
    "stem": ("STEM", "science technology engineering and mathematics"), "ngo": ("NGO", "non-governmental organisation"),
    "ngos": ("NGOs", "non-governmental organisations"), "gis": ("GIS", "geographic information system"),
    "uav": ("UAV", "unmanned aerial vehicle"), "uavs": ("UAVs", "unmanned aerial vehicles"),
    "b2b": ("B2B", "business-to-business"), "b2c": ("B2C", "business-to-consumer"),
    "lmic": ("LMIC", "low- and middle-income country"), "lmics": ("LMICs", "low- and middle-income countries"),
}

# Verbs that join two concepts ("microfinance REDUCE poverty"). A phrase is split where they appear.
# Words that are also common nouns in research phrases ("social support", "health benefits") are left out.
VERBS = {"affect", "predict", "reduce", "increase", "decrease", "enhance", "boost", "drive", "shape", "play",
         "enable", "hinder", "promote", "determine", "explain", "mediate", "moderate", "cause", "lead", "contribute",
         "transform", "relate", "compare", "differ", "vary", "matter", "achieve", "become", "remain", "exist",
         "occur", "emerge", "require", "depend", "facilitate", "foster", "undermine", "mitigate", "address",
         "tackle", "prevent", "encourage", "motivate", "perceive", "adopt", "shift", "impede", "constrain",
         "accelerate", "slow", "delay", "worsen", "improve", "strengthen", "weaken", "alter", "create", "generate", "produce", "provide", "allow", "show",
         "assist", "inform", "guide", "limit", "threaten", "harm", "protect"}

# Evaluative and framing words that never name a topic.
EVALUATIVE = {"effective", "effectiveness", "efficient", "successful", "success", "important", "importance", "useful",
              "usefulness", "good", "better", "best", "bad", "worse", "major", "minor", "potential", "possible", "various",
              "different", "certain", "specific", "overall", "general", "future", "present", "existing", "determinants",
              "drivers", "association", "associations", "link", "links", "nexus", "relation", "relations", "part",
              "aspects", "aspect", "dimension", "dimensions", "evidence-based", "empirical", "systematic", "review"}

# Nouns that are vague on their own but complete a phrase when they follow a topic word:
# "patient outcomes", "ESG performance", "firm value", "investment decisions".
SOFT_HEADS = {"outcome", "outcomes", "performance", "behaviour", "behavior", "behaviours", "behaviors", "value", "values",
              "decision", "decisions", "quality", "growth", "intention", "intentions", "usage", "use", "engagement",
              "satisfaction", "management", "practices", "policy", "policies", "adoption"}
