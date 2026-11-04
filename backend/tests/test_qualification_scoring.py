"""Unit tests for QualificationEngine scoring logic:
- Ensures absence of a feature NEVER implies buying intent.
- Verifies separate dimensions: Business Quality, Service Opportunity, Conversion Potential, Evidence Confidence.
- Tests misleading signals: missing video, missing analytics, missing chatbot, missing e-commerce.
"""
import pytest
from app.research.qualification_engine import QualificationEngine


def test_missing_video_does_not_imply_buying_intent():
    """Missing video on landing page must not result in an inflated score or high confidence."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reliable Logistics Pvt Ltd</title>
        <meta name="description" content="Leading freight forwarding and supply chain solutions in Bengaluru.">
    </head>
    <body>
        <h1>Reliable Logistics</h1>
        <p>Contact us for freight quotes across India.</p>
        <form action="/contact"><input name="email" type="email"><button>Submit</button></form>
    </body>
    </html>
    """
    result = QualificationEngine.analyze("https://reliablelogistics.example.com", html, business_name="Reliable Logistics")
    video_opp = next(o for o in result['opportunities'] if o['service'] == 'Video Editing')

    # Must be exploratory, not inflated
    assert video_opp['score'] <= 30
    assert video_opp['confidence'] == 'low'
    assert video_opp['buying_intent_status'] == 'unknown'
    assert 'appetite' in video_opp['reason'].lower() or 'unknown' in video_opp['reason'].lower()
    assert 'No video media' in video_opp['observed_technical_state']


def test_video_presence_scores_active_media_investment():
    """Presence of video indicates active media creator with legitimate editing opportunities."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Innovative EdTech Bangalore</title>
    </head>
    <body>
        <h1>EdTech Platform</h1>
        <iframe src="https://www.youtube.com/embed/sample123"></iframe>
        <video controls><source src="intro.mp4" type="video/mp4"></video>
    </body>
    </html>
    """
    result = QualificationEngine.analyze("https://edtech.example.com", html, business_name="Innovative EdTech")
    video_opp = next(o for o in result['opportunities'] if o['service'] == 'Video Editing')

    assert video_opp['score'] >= 50
    assert video_opp['confidence'] == 'high'
    assert 'Video embeds or interactive media detected' in video_opp['observed_technical_state']


def test_missing_chatbot_does_not_inflate_ai_automation_intent():
    """Missing chatbot must be recorded as an observed technical state, not confirmed intent."""
    html = """
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>City Clinic</title></head>
    <body>
        <form action="/book"><input name="patient"><button>Book</button></form>
    </body>
    </html>
    """
    result = QualificationEngine.analyze("https://cityclinic.example.com", html, business_name="City Clinic")
    ai_opp = next(o for o in result['opportunities'] if o['service'] == 'AI Automation')

    assert ai_opp['score'] <= 40
    assert ai_opp['buying_intent_status'] == 'unknown'
    assert 'exploratory' in ai_opp['reason'].lower() or 'unconfirmed' in ai_opp['reason'].lower()


def test_missing_ecommerce_scores_low_and_unconfirmed():
    """Absence of e-commerce must NOT generate high opportunity score."""
    html = """
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Corporate Law Firm</title></head>
    <body><p>Legal advisory services</p></body>
    </html>
    """
    result = QualificationEngine.analyze("https://lawfirm.example.com", html, business_name="Corporate Law")
    ecom_opp = next(o for o in result['opportunities'] if o['service'] == 'E-commerce Development')

    assert ecom_opp['score'] <= 15
    assert ecom_opp['confidence'] == 'low'
    assert ecom_opp['buying_intent_status'] == 'unknown'
    assert 'does not indicate demand' in ecom_opp['reason'].lower()


def test_missing_analytics_recorded_as_technical_observation_not_agency_intent():
    """Absence of analytics script is a technical observation, not proven intent to buy SEO."""
    html = """
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Modern Tech Hub</title></head>
    <body><p>Consulting</p></body>
    </html>
    """
    result = QualificationEngine.analyze("https://techhub.example.com", html, business_name="Modern Tech Hub")
    seo_opp = next(o for o in result['opportunities'] if o['service'] == 'SEO and Digital Marketing')

    assert seo_opp['score'] <= 50
    assert seo_opp['buying_intent_status'] == 'unknown'
    assert 'requires validating marketing goals' in seo_opp['reason'].lower()


def test_independent_dimensions_separated():
    """Business Quality, Conversion Potential, and Service Opportunities must remain strictly separate."""
    # A top-tier, modern website: high quality, but service opportunity scores should be low!
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fintech Leaders India - Payment Gateway Solutions</title>
        <meta name="description" content="Award-winning payment infrastructure for Indian enterprises and startups.">
        <script src="https://www.googletagmanager.com/gtag/js"></script>
    </head>
    <body>
        <h1>Enterprise Payment Gateway</h1>
        <form action="/demo"><input type="email" name="work_email"><button>Request Demo</button></form>
        <a href="https://linkedin.com/company/fintechleaders">LinkedIn</a>
        <a href="https://twitter.com/fintechleaders">Twitter</a>
        <div class="cart-items">Active Checkout Infrastructure</div>
    </body>
    </html>
    """
    result = QualificationEngine.analyze("https://fintechleaders.in", html, business_name="Fintech Leaders India")

    # Business Quality must be high due to HTTPS, viewport, title, description, social links
    assert result['business_quality'] >= 75

    # Conversion Potential must be high due to form, analytics, cart, social links
    assert result['conversion_potential'] >= 70

    # Website Development opportunity should be LOW because the site is already modern and responsive
    web_opp = next(o for o in result['opportunities'] if o['service'] == 'Website Development')
    assert web_opp['score'] <= 35

    # Evidence confidence must be high
    assert result['evidence_confidence'] == 'high'
    assert len(result['evidence']) >= 5

    # Missing info must explicitly log unobserved business factors
    assert any('budget' in m.lower() for m in result['missing_information'])
    assert any('contract' in m.lower() for m in result['missing_information'])

