"""Websites that many businesses share, so their domain identifies nobody.

A company's own domain is strong evidence of identity: two listings with the same
website are usually one business. That breaks when the page lives somewhere many
businesses share: a site builder, a social profile, a directory entry, a booking
tool, a manufacturer's dealer page, or a national franchise brand. Two unrelated
businesses on one site builder would otherwise merge, and each would be dated by the
platform's registration rather than its own.

For matching and for domain age such a website counts as no domain at all. The page
itself is kept on the company, and can still be read.

This list is curated rather than complete. Matching does not depend on it alone: a
shared website with different names, pages or places still goes to review.
"""

from __future__ import annotations

from dealsignal.matching.normalize import normalize_domain

SITE_BUILDERS = frozenset(
    {
        "business.site",
        "wixsite.com",
        "wix.com",
        "editorx.io",
        "godaddysites.com",
        "godaddy.com",
        "square.site",
        "squareup.com",
        "squarespace.com",
        "weebly.com",
        "weeblysite.com",
        "wordpress.com",
        "blogspot.com",
        "blogger.com",
        "webflow.io",
        "myshopify.com",
        "carrd.co",
        "jimdosite.com",
        "jimdofree.com",
        "site123.me",
        "ueniweb.com",
        "yolasite.com",
        "homestead.com",
        "webs.com",
        "strikingly.com",
        "mystrikingly.com",
        "multiscreensite.com",
        "mailchimpsites.com",
        "hubspotpagebuilder.com",
        "netlify.app",
        "vercel.app",
        "github.io",
        "herokuapp.com",
        "azurewebsites.net",
        "firebaseapp.com",
        "web.app",
        "pages.dev",
        "linktr.ee",
        "beacons.ai",
        "bio.link",
    }
)

MAPS_AND_SOCIAL = frozenset(
    {
        "google.com",
        "google.co.uk",
        "google.fr",
        "g.page",
        "goo.gl",
        "apple.com",
        "bing.com",
        "facebook.com",
        "fb.com",
        "fb.me",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "youtu.be",
        "tiktok.com",
        "pinterest.com",
        "nextdoor.com",
        "threads.net",
        "whatsapp.com",
        "wa.me",
    }
)

DIRECTORIES = frozenset(
    {
        "yelp.com",
        "yellowpages.com",
        "yp.com",
        "superpages.com",
        "bbb.org",
        "angi.com",
        "angieslist.com",
        "homeadvisor.com",
        "thumbtack.com",
        "houzz.com",
        "porch.com",
        "bark.com",
        "buildzoom.com",
        "manta.com",
        "mapquest.com",
        "foursquare.com",
        "tripadvisor.com",
        "nicelocal.com",
        "trustab.org",
        "chamberofcommerce.com",
        "alignable.com",
        "birdeye.com",
        "merchantcircle.com",
        "hotfrog.com",
        "brownbook.net",
        "zocdoc.com",
        "healthgrades.com",
        "opencare.com",
        "vitals.com",
        "trustpilot.com",
        "checkatrade.com",
        "mybuilder.com",
        "ratedpeople.com",
        "trustatrader.com",
        "yell.com",
        "which.co.uk",
        "freeindex.co.uk",
        "thomsonlocal.com",
        "pagesjaunes.fr",
        "societe.com",
        "doctolib.fr",
    }
)

BOOKING_TOOLS = frozenset(
    {
        "housecallpro.com",
        "getjobber.com",
        "jobber.com",
        "servicetitan.com",
        "setmore.com",
        "calendly.com",
        "vagaro.com",
        "schedulicity.com",
        "acuityscheduling.com",
        "booksy.com",
        "fresha.com",
        "nexhealth.com",
    }
)

MANUFACTURERS = frozenset(
    {
        "lennox.com",
        "carrier.com",
        "trane.com",
        "rheem.com",
        "ruud.com",
        "goodmanmfg.com",
        "amana-hac.com",
        "bryant.com",
        "americanstandardair.com",
        "daikincomfort.com",
        "mitsubishicomfort.com",
        "frigidaire.net",
        "frigidaire.com",
        "york.com",
        "heil-hvac.com",
        "tempstar.com",
        "payne.com",
        "generac.com",
        "kohler.com",
        "bradfordwhite.com",
        "worcester-bosch.co.uk",
        "vaillant.co.uk",
        "baxi.co.uk",
        "idealheating.com",
        "intuit.com",
    }
)
"""Dealer and locator pages. intuit.com is here because Overture lists local tax
offices under turbotax.intuit.com, and 1994 is Intuit's domain, not theirs."""

FRANCHISE_BRANDS = frozenset(
    {
        "aireserv.com",
        "onehourheatandair.com",
        "benjaminfranklinplumbing.com",
        "mrrooter.com",
        "rotorooter.com",
        "servicexperts.com",
        "temperaturepro.com",
        "mistersparky.com",
        "mrelectric.com",
        "mrhandyman.com",
        "ars.com",
        "stanleysteemer.com",
        "chemdry.com",
        "servpro.com",
        "servicemaster.com",
        "puroclean.com",
        "rainbowintl.com",
        "mollymaid.com",
        "merrymaids.com",
        "aspendental.com",
        "castledental.com",
        "smilegeneration.com",
        "taxassist.co.uk",
    }
)
"""Networks of separately owned locations under one website. The domain is the
brand's, so it identifies no single franchisee and dates none of them."""

SHARED_DOMAINS: frozenset[str] = (
    SITE_BUILDERS | MAPS_AND_SOCIAL | DIRECTORIES | BOOKING_TOOLS | MANUFACTURERS | FRANCHISE_BRANDS
)


def is_shared_domain(domain: str | None) -> bool:
    return domain is not None and domain in SHARED_DOMAINS


def identity_domain(url: str | None) -> str | None:
    """The website domain that identifies a business, or None when it is shared.

    >>> identity_domain("https://example-hvac.business.site/")
    >>> identity_domain("https://www.checkmyac.com/about-us")
    'checkmyac.com'
    """
    domain = normalize_domain(url)
    return None if is_shared_domain(domain) else domain
