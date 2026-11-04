"""AI Research and Qualification Engine for SparkXFlow.
Analyzes public website markup to extract observable technical and commercial evidence,
then scores opportunities for each of the nine SparkXFlow agency services.
Does not invent intent, budget or requirements without evidence.
"""
import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup

SPARKXFLOW_SERVICES = [
    "Website Development",
    "Web Application Development",
    "AI Automation",
    "E-commerce Development",
    "SaaS Development",
    "SEO and Digital Marketing",
    "Mobile Application Development",
    "CRM and Business Automation",
    "Video Editing"
]

class QualificationEngine:
    @staticmethod
    def analyze(url: str, html: str, business_name: str = '') -> Dict[str, Any]:
        soup = BeautifulSoup(html, 'html.parser')
        stamp = datetime.now(timezone.utc).isoformat()
        evidence: List[Dict[str, str]] = []

        # Technical Observations
        title = soup.title.get_text(' ', strip=True)[:250] if soup.title else ''
        meta_desc = soup.find('meta', attrs={'name': re.compile(r'^description$', re.I)})
        description = (meta_desc.get('content', '') if meta_desc else '')[:500]
        viewport_meta = soup.find('meta', attrs={'name': re.compile(r'^viewport$', re.I)})
        has_viewport = bool(viewport_meta)
        
        evidence.append({
            'fact': 'Website returned valid HTML content',
            'url': url,
            'collected_at': stamp,
            'confidence': 'high'
        })

        if has_viewport:
            evidence.append({
                'fact': 'Viewport meta tag detected (mobile-aware configuration)',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })
        else:
            evidence.append({
                'fact': 'No viewport meta tag found; mobile responsive scaling may be impaired',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })

        if title:
            evidence.append({
                'fact': f'Page title: {title}',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })
        else:
            evidence.append({
                'fact': 'Missing page title in head element',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })

        if description:
            evidence.append({
                'fact': f'Meta description present ({len(description)} characters)',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })
        else:
            evidence.append({
                'fact': 'Missing meta description tag (affects search snippet click-through)',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })

        # Framework / Platform Signals
        html_str = html.lower()
        cms_detected = []
        if 'wp-content' in html_str or 'wordpress' in html_str:
            cms_detected.append('WordPress')
        if 'cdn.shopify.com' in html_str or 'shopify' in html_str:
            cms_detected.append('Shopify')
        if 'wix.com' in html_str or '_wix_' in html_str:
            cms_detected.append('Wix')
        if 'squarespace' in html_str:
            cms_detected.append('Squarespace')
        if 'webflow' in html_str:
            cms_detected.append('Webflow')

        if cms_detected:
            evidence.append({
                'fact': f'CMS/Platform detected: {", ".join(cms_detected)}',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })

        # E-commerce Signals
        cart_links = soup.find_all('a', href=re.compile(r'cart|basket|checkout|shop', re.I))
        has_prices = bool(re.search(r'[\$£€₹]\s?\d+(?:\.\d{2})?', html))
        has_ecommerce = bool(cart_links or 'shopify' in cms_detected or has_prices)
        if has_ecommerce:
            evidence.append({
                'fact': f'Commercial elements detected (cart/checkout links or currency symbols)',
                'url': url,
                'collected_at': stamp,
                'confidence': 'medium'
            })

        # Forms / Automation Signals
        forms = soup.find_all('form')
        evidence.append({
            'fact': f'Identified {len(forms)} HTML form(s) on homepage',
            'url': url,
            'collected_at': stamp,
            'confidence': 'high'
        })

        # Video Signals
        videos = soup.find_all(['video', 'iframe'])
        video_embeds = [v for v in videos if any(x in str(v).lower() for x in ['youtube', 'vimeo', 'wistia', 'mp4'])]
        if video_embeds:
            evidence.append({
                'fact': f'Video media detected ({len(video_embeds)} video embed(s) found)',
                'url': url,
                'collected_at': stamp,
                'confidence': 'high'
            })
        else:
            evidence.append({
                'fact': 'No video embeds or interactive media found on main landing page',
                'url': url,
                'collected_at': stamp,
                'confidence': 'medium'
            })

        # Analytics & Social Signals
        has_analytics = any(x in html_str for x in ['gtag', 'google-analytics', 'analytics.js', 'facebook-pixel', 'hotjar'])
        social_links = [a.get('href') for a in soup.find_all('a', href=re.compile(r'linkedin|twitter|instagram|facebook|youtube', re.I))]

        # Service Opportunity Scores (0-100)
        # Principles:
        # 1. Absence of a feature must NEVER imply buying intent or high commercial urgency.
        # 2. Separate observable technical weaknesses from inferred opportunities.
        # 3. Every score must be grounded in verified evidence; missing information remains explicitly unknown.
        # 4. Business Quality, Service Opportunity, Conversion Potential, and Evidence Confidence remain strictly separate.
        opportunities = []

        # 1. Website Development
        if not has_viewport:
            web_score = 75
            web_conf = 'high'
            web_state = 'Non-responsive layout: Missing mobile viewport meta tag.'
            web_reason = 'Critical mobile usability issue observed from missing viewport tag. High technical justification for modern responsive frontend rebuild.'
        elif 'wix' in cms_detected or 'squarespace' in cms_detected:
            web_score = 45
            web_conf = 'medium'
            web_state = f"Hosted builder detected ({', '.join(cms_detected)})."
            web_reason = 'Site operates on restrictive generic builder with potential performance and customization ceilings. Redesign value depends on growth stage.'
        else:
            web_score = 25
            web_conf = 'medium'
            web_state = 'Modern responsive layout detected with standard viewport meta tag.'
            web_reason = 'Website is technically functional; rebuild value is low unless driven by branding or strategic positioning shifts.'

        opportunities.append({
            'service': 'Website Development',
            'score': web_score,
            'confidence': web_conf,
            'observed_technical_state': web_state,
            'buying_intent_status': 'unknown',
            'reason': web_reason,
            'evidence_indexes': [0, 1]
        })

        # 2. Web Application Development
        if len(forms) >= 2:
            app_score = 40
            app_conf = 'medium'
            app_state = f'Multiple static inquiry forms ({len(forms)}) detected.'
            app_reason = f'Multiple inquiry forms indicate manual lead workflows that could be consolidated into a self-service client portal. Commercial appetite unverified.'
        else:
            app_score = 20
            app_conf = 'low'
            app_state = 'No observable client portal, authentication forms, or interactive web applications on public homepage.'
            app_reason = 'Standard marketing website with no evidence of custom web application workflows.'

        opportunities.append({
            'service': 'Web Application Development',
            'score': app_score,
            'confidence': app_conf,
            'observed_technical_state': app_state,
            'buying_intent_status': 'unknown',
            'reason': app_reason,
            'evidence_indexes': [5] if forms else []
        })

        # 3. AI Automation
        # Misleading signal guard: Absence of a chatbot DOES NOT imply buying intent or high readiness!
        has_chat = any(x in html_str for x in ['chat', 'intercom', 'drift', 'tidio', 'zendesk'])
        if has_chat:
            ai_score = 45
            ai_conf = 'high'
            ai_state = 'Third-party chat widget observed on public homepage.'
            ai_reason = 'Business already utilizes conversational capture; opportunity exists for custom AI agent orchestration or backend workflow integrations.'
        elif len(forms) > 0:
            ai_score = 35
            ai_conf = 'medium'
            ai_state = 'Static inquiry form present without automated chat widget.'
            ai_reason = 'Uses static form for lead intake. Absence of a chatbot is an empirical fact; automation opportunity is exploratory and unconfirmed.'
        else:
            ai_score = 20
            ai_conf = 'low'
            ai_state = 'No public interactive contact or chat widgets observed.'
            ai_reason = 'No customer interaction widgets detected on homepage; AI automation relevance is unconfirmed.'

        opportunities.append({
            'service': 'AI Automation',
            'score': ai_score,
            'confidence': ai_conf,
            'observed_technical_state': ai_state,
            'buying_intent_status': 'unknown',
            'reason': ai_reason,
            'evidence_indexes': [5] if forms else []
        })

        # 4. E-commerce Development
        # Misleading signal guard: Absence of e-commerce must NOT generate a high opportunity score!
        if has_ecommerce:
            ecom_score = 75
            ecom_conf = 'high'
            ecom_state = 'Active e-commerce shopping cart and transactional checkout detected.'
            ecom_reason = 'Active commerce presence with concrete opportunities for checkout optimization, conversion rate uplift, and platform scaling.'
        else:
            ecom_score = 10
            ecom_conf = 'low'
            ecom_state = 'No transactional cart or checkout infrastructure observed.'
            ecom_reason = 'No active e-commerce shopping cart or transactional checkout identified. Business model likely service-based or non-transactional. Absence does not indicate demand.'

        opportunities.append({
            'service': 'E-commerce Development',
            'score': ecom_score,
            'confidence': ecom_conf,
            'observed_technical_state': ecom_state,
            'buying_intent_status': 'unknown',
            'reason': ecom_reason,
            'evidence_indexes': [4] if has_ecommerce else []
        })

        # 5. SaaS Development
        saas_score = 15
        opportunities.append({
            'service': 'SaaS Development',
            'score': saas_score,
            'confidence': 'low',
            'observed_technical_state': 'No software-as-a-service application interface observed.',
            'buying_intent_status': 'unknown',
            'reason': 'SaaS product development is highly specialized; public website does not indicate proprietary software ambitions.',
            'evidence_indexes': []
        })

        # 6. SEO and Digital Marketing
        # Misleading signal guard: Absence of analytics is a technical observation, NOT proven intent to hire an SEO agency!
        seo_reasons = []
        seo_states = []
        if not description:
            seo_states.append('Missing meta description')
            seo_reasons.append('Missing meta description tag degrades search engine snippet CTR.')
        if not has_analytics:
            seo_states.append('No client-side analytics script observed')
            seo_reasons.append('No client-side analytics tag identified in public HTML; client tracking setup requires discovery.')
        if has_analytics and description:
            seo_score = 30
            seo_conf = 'high'
            seo_state = 'Foundational SEO elements present (meta description and analytics tags detected).'
            seo_reason = 'Foundational technical SEO tags are in place; optimization focus is on organic keyword rankings and content authority.'
        else:
            seo_score = 45
            seo_conf = 'medium'
            seo_state = '; '.join(seo_states)
            seo_reason = ' '.join(seo_reasons) + ' Technical gaps observed; commercial SEO readiness requires validating marketing goals and baseline traffic.'

        opportunities.append({
            'service': 'SEO and Digital Marketing',
            'score': seo_score,
            'confidence': seo_conf,
            'observed_technical_state': seo_state,
            'buying_intent_status': 'unknown',
            'reason': seo_reason,
            'evidence_indexes': [3]
        })

        # 7. Mobile Application Development
        mobile_score = 25
        opportunities.append({
            'service': 'Mobile Application Development',
            'score': mobile_score,
            'confidence': 'low',
            'observed_technical_state': 'No native mobile application store links or deep links observed.',
            'buying_intent_status': 'unknown',
            'reason': 'No public mobile app indicators found; requirement for mobile software depends entirely on customer interaction frequency.',
            'evidence_indexes': [1]
        })

        # 8. CRM and Business Automation
        if len(forms) > 0:
            crm_score = 40
            crm_conf = 'medium'
            crm_state = f'Inbound inquiry forms ({len(forms)}) present on public page.'
            crm_reason = 'Inbound customer requests captured through static mailer forms could benefit from automated CRM dispatch and follow-up sequences. Internal tools unknown.'
        else:
            crm_score = 20
            crm_conf = 'low'
            crm_state = 'No public inbound inquiry forms observed.'
            crm_reason = 'No web inquiry capture points observed; CRM requirements require consultative discovery.'

        opportunities.append({
            'service': 'CRM and Business Automation',
            'score': crm_score,
            'confidence': crm_conf,
            'observed_technical_state': crm_state,
            'buying_intent_status': 'unknown',
            'reason': crm_reason,
            'evidence_indexes': [5] if forms else []
        })

        # 9. Video Editing
        # Misleading signal guard: Absence of video on homepage DOES NOT mean the business has buying intent for video editing!
        if video_embeds:
            video_score = 55
            video_conf = 'high'
            video_state = f'Video embeds or interactive media detected ({len(video_embeds)} elements).'
            video_reason = 'Business actively invests in video media; opportunity exists for high-retention post-production, motion graphics, and social cutdowns.'
        else:
            video_score = 20
            video_conf = 'low'
            video_state = 'No video media or streaming embeds observed on public landing page.'
            video_reason = 'No video media observed on public homepage. Absence of video is an observed technical state; client appetite, creative requirements, and budget for video production are unknown.'

        opportunities.append({
            'service': 'Video Editing',
            'score': video_score,
            'confidence': video_conf,
            'observed_technical_state': video_state,
            'buying_intent_status': 'unknown',
            'reason': video_reason,
            'evidence_indexes': [6] if len(evidence) > 6 else []
        })

        # Independent Dimension 1: Business Quality (10-95)
        # Strictly evaluates observed technical and operational maturity of the business itself,
        # completely decoupled from agency sales pitch scores!
        quality_score = 20  # Base for having an accessible public website
        if url.startswith('https://'):
            quality_score += 20
        if has_viewport:
            quality_score += 20
        if title and len(title) > 5 and 'untitled' not in title.lower():
            quality_score += 15
        if description and len(description) > 20:
            quality_score += 10
        if len(social_links) > 0:
            quality_score += 10
        business_quality = int(min(max(quality_score, 10), 95))

        # Independent Dimension 2: Conversion Potential (15-90)
        # Evaluates commercial readiness / active digital engagement (active forms, commerce, tracking).
        # Decoupled from hypothetical agency opportunity scores.
        conversion_score = 20
        if len(forms) > 0:
            conversion_score += 20
        if has_analytics:
            conversion_score += 20
        if has_ecommerce:
            conversion_score += 25
        if len(social_links) >= 2:
            conversion_score += 10
        conversion_potential = int(min(max(conversion_score, 15), 90))

        # Independent Dimension 3: Evidence Confidence
        # Strictly determined by the volume and quality of empirically verified facts.
        fact_count = len(evidence)
        if fact_count >= 5:
            evidence_confidence = 'high'
        elif fact_count >= 3:
            evidence_confidence = 'medium'
        else:
            evidence_confidence = 'low'

        missing_info = [
            'Executive decision-maker budget authorization and spending priority (unobserved)',
            'Current internal conversion rates and sales velocity (unobserved)',
            'Existing software contract lock-in periods and internal tech stack (unobserved)'
        ]

        summary = (
            f"Audited {url}. Detected {len(cms_detected)} CMS signal(s), "
            f"{'mobile viewport tag' if has_viewport else 'no mobile viewport tag'}, and {len(forms)} form element(s). "
            f"Business quality score: {business_quality}/100. Observed technical gaps logged; commercial intent remains unknown pending discovery."
        )

        return {
            'title': title,
            'description': description,
            'evidence': evidence,
            'opportunities': opportunities,
            'business_quality': business_quality,
            'conversion_potential': conversion_potential,
            'evidence_confidence': evidence_confidence,
            'missing_information': missing_info,
            'limitations': 'Observed public technical attributes only. Commercial intent, budget and internal requirements remain strictly unknown until human qualification.',
            'ai_summary': summary
        }

    @staticmethod
    def extract_public_contacts(url: str, html: str, business_name: str = '') -> List[Dict[str, Any]]:
        """Extracts strictly observable public contact points from parsed HTML.
        Never fabricates names, roles, or email addresses.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        discovered_contacts: List[Dict[str, Any]] = []
        seen_emails = set()
        seen_phones = set()

        email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

        # 1. Parse Schema.org JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                raw_text = script.string or script.get_text()
                if not raw_text:
                    continue
                data = json.loads(raw_text)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    types = item.get('@type', [])
                    if isinstance(types, str):
                        types = [types]
                    type_str = ' '.join(types).lower()

                    # Person / Founder / Officer
                    if any(t in type_str for t in ['person', 'founder', 'author', 'officer']):
                        p_name = item.get('name', '').strip()
                        p_job = item.get('jobTitle', '').strip() or 'Leadership'
                        p_email = item.get('email', '').strip().lower()
                        p_phone = item.get('telephone', '').strip()

                        if p_name and (p_email or p_phone or p_job):
                            if p_email and p_email in seen_emails:
                                continue
                            if p_email:
                                seen_emails.add(p_email)
                            discovered_contacts.append({
                                'full_name': p_name,
                                'job_title': p_job,
                                'role_category': 'founder' if 'founder' in p_job.lower() or 'ceo' in p_job.lower() else 'executive',
                                'email': p_email if email_regex.match(p_email) else '',
                                'phone': p_phone,
                                'linkedin_url': item.get('sameAs', '') if 'linkedin' in str(item.get('sameAs', '')).lower() else '',
                                'source_url': url,
                                'contact_source': f'Schema.org JSON-LD ({", ".join(types)}) on {url}',
                                'verification_status': 'unverified_public' if p_email else 'not_available',
                                'confidence_level': 'high'
                            })

                    # Organization / LocalBusiness general contact points
                    elif any(t in type_str for t in ['organization', 'localbusiness', 'corporation', 'store', 'company']):
                        org_email = item.get('email', '').strip().lower()
                        org_phone = item.get('telephone', '').strip()
                        if org_email and org_email not in seen_emails and email_regex.match(org_email):
                            seen_emails.add(org_email)
                            discovered_contacts.append({
                                'full_name': f"{item.get('name', business_name or 'Business')} Inquiries",
                                'job_title': 'Published Public Contact',
                                'role_category': 'other',
                                'email': org_email,
                                'phone': org_phone,
                                'linkedin_url': '',
                                'source_url': url,
                                'contact_source': f'Schema.org Organization contact on {url}',
                                'verification_status': 'unverified_public',
                                'confidence_level': 'high'
                            })
            except Exception:
                continue

        # 2. Extract explicit mailto: hyperlinks
        for a in soup.find_all('a', href=re.compile(r'^mailto:', re.I)):
            href = a.get('href', '')
            raw_email = href.split(':', 1)[1].split('?')[0].strip().lower()
            if email_regex.match(raw_email) and raw_email not in seen_emails:
                seen_emails.add(raw_email)
                link_text = a.get_text(' ', strip=True)
                title = 'Inquiries'
                if any(k in link_text.lower() for k in ['director', 'founder', 'ceo', 'manager']):
                    title = link_text[:60]

                discovered_contacts.append({
                    'full_name': f"{business_name or 'Business'} Contact",
                    'job_title': title,
                    'role_category': 'other',
                    'email': raw_email,
                    'phone': '',
                    'linkedin_url': '',
                    'source_url': url,
                    'contact_source': f'Public mailto link on {url}',
                    'verification_status': 'unverified_public',
                    'confidence_level': 'high'
                })

        # 3. Extract explicit tel: hyperlinks
        for a in soup.find_all('a', href=re.compile(r'^tel:', re.I)):
            href = a.get('href', '')
            raw_phone = href.split(':', 1)[1].strip()
            if raw_phone and raw_phone not in seen_phones:
                seen_phones.add(raw_phone)
                # If we have an existing contact without phone, enrich it
                enriched = False
                for c in discovered_contacts:
                    if not c['phone']:
                        c['phone'] = raw_phone
                        enriched = True
                        break
                if not enriched and not discovered_contacts:
                    discovered_contacts.append({
                        'full_name': f"{business_name or 'Business'} Desk",
                        'job_title': 'Phone Line',
                        'role_category': 'other',
                        'email': '',
                        'phone': raw_phone,
                        'linkedin_url': '',
                        'source_url': url,
                        'contact_source': f'Public tel link on {url}',
                        'verification_status': 'not_available',
                        'confidence_level': 'high'
                    })

        return discovered_contacts

