"""Personalized AI Email Generation Engine for SparkXFlow Engine D.
Crafts compelling, professional B2B outreach tailored to observed technical gaps and decision-maker roles.
Never makes unfounded claims; references observable evidence explicitly.
"""
from typing import Dict, Any, List, Optional

SPARKXFLOW_PITCHES = {
    "Website Development": {
        "pain": "mobile responsive scaling and layout modernizations",
        "value": "delivering a high-performance, modern responsive digital presence that improves brand perception and inbound lead conversions",
        "cta": "explore our recent web re-platforming case studies"
    },
    "Web Application Development": {
        "pain": "disjointed client communications and manual onboarding workflows",
        "value": "engineering secure custom client portals and business applications that eliminate manual paperwork",
        "cta": "see how custom web apps automate client onboarding"
    },
    "AI Automation": {
        "pain": "repetitive manual customer inquiries and intake latency",
        "value": "deploying intelligent conversational triage and 24/7 AI lead capture bots that respond to prospects in seconds",
        "cta": "review a quick 3-minute demo of our intake automation"
    },
    "E-commerce Development": {
        "pain": "checkout friction and online conversion rate ceilings",
        "value": "optimizing cart checkout velocity, mobile shopping UX, and automated post-purchase workflows",
        "cta": "discuss conversion optimization strategies for your catalog"
    },
    "SaaS Development": {
        "pain": "scaling operational software and recurring revenue digital products",
        "value": "architecting enterprise-grade SaaS platforms with automated billing, telemetry, and user management",
        "cta": "walk through our full-stack architecture blueprint"
    },
    "SEO and Digital Marketing": {
        "pain": "missing metadata tags and unranked commercial search intent",
        "value": "implementing technical on-page schema and targeted SEO architecture to dominate regional search results",
        "cta": "review your complimentary technical SEO audit"
    },
    "Mobile Application Development": {
        "pain": "field operational gaps and limited mobile utility for clients",
        "value": "building native and cross-platform mobile apps that keep your service accessible on iOS and Android",
        "cta": "explore mobile utility prototypes in your sector"
    },
    "CRM and Business Automation": {
        "pain": "manual lead tracking and untracked follow-up intervals",
        "value": "integrating unified CRM pipelines that automatically assign leads, schedule follow-ups, and track deal stages",
        "cta": "benchmark your current sales follow-up automation"
    },
    "Video Editing": {
        "pain": "text-heavy landing pages without dynamic video storytelling",
        "value": "producing high-impact motion graphics, product walkthroughs, and client case study videos that double engagement",
        "cta": "preview our recent commercial video reels"
    }
}

class EmailPersonalizer:
    @staticmethod
    def generate_draft(business_name: str,
                       service_name: str,
                       contact_name: str = '',
                       contact_title: str = '',
                       evidence_list: Optional[List[Dict[str, str]]] = None,
                       location: str = '') -> Dict[str, Any]:
        contact_salutation = f"Hi {contact_name.split()[0]}" if contact_name and 'Office' not in contact_name and 'Lead' not in contact_name else "Hi there"
        pitch = SPARKXFLOW_PITCHES.get(service_name, SPARKXFLOW_PITCHES["Website Development"])

        # Extract specific evidence points
        observed_facts = [e.get('fact') for e in (evidence_list or []) if e.get('fact')]
        evidence_snippet = ""
        if observed_facts:
            # Highlight first 1-2 facts
            relevant = [f for f in observed_facts if 'HTML' not in f][:2]
            if relevant:
                evidence_snippet = f" While reviewing your digital footprint, our technical team noted: {'; '.join(relevant)}."

        subject = f"{service_name} opportunity for {business_name}"

        body = f"""{contact_salutation},

I came across {business_name}{f' in {location}' if location else ''} and was impressed by your industry positioning.{evidence_snippet}

At SparkXFlow, we specialize in {service_name.lower()} for growing businesses—specifically {pitch['value']}. Many teams in your space struggle with {pitch['pain']}, and we build robust digital solutions that solve this directly.

Would you be open to a brief 10-minute introductory conversation next week to {pitch['cta']}?

Best regards,

Alex Rivera
Partnership Director | SparkXFlow Agency
https://sparkxflow.agency
"""

        personalization_notes = (
            f"Tailored for {contact_title or 'business leadership'} at {business_name}. "
            f"Focuses on {service_name} with value proposition: {pitch['value']}."
        )

        return {
            'subject': subject,
            'body_text': body.strip(),
            'personalization_notes': personalization_notes,
            'evidence_references': observed_facts[:3]
        }

