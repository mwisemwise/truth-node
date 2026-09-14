import os

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def build_pdf(filename="Highway_248_Synergy_Audit.pdf", biz_name="Bob's Plumbing"):

    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()

    # Custom Palette
    PRIMARY = colors.HexColor("#004488")
    ACCENT_RED = colors.HexColor("#D32F2F")
    BG_LIGHT = colors.HexColor("#F8F9FA")
    TEXT_DARK = colors.HexColor("#212121")

    # Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        textColor=PRIMARY,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        spaceAfter=15
    )

    h2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        textColor=PRIMARY,
        spaceBefore=12,
        spaceAfter=8
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=TEXT_DARK,
        spaceAfter=8
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=ACCENT_RED,
        alignment=1  # Center
    )

    story = []

    # =========================================================================
    # PAGE 1: THE HOOK, SCORE & GOOGLE 23% STAT
    # =========================================================================

    story.append(Paragraph("HIGHWAY 248 LOCAL SYNERGY &amp; AI AUDIT", title_style))
    story.append(Paragraph(f"Prepared for: <b>{biz_name}</b> | Corridor Analysis | Status: <b>ACTION REQUIRED</b>", subtitle_style))
    story.append(Spacer(1, 10))

    # Score Box Table
    score_data = [
        [Paragraph("<font size=12 color='#ffffff'>LOCAL DATA CONFIDENCE SCORE</font>", ParagraphStyle('SB1', alignment=1)),
         Paragraph("<font size=12 color='#ffffff'>CORRIDOR RANK</font>", ParagraphStyle('SB2', alignment=1))],
        [Paragraph("<font size=36 color='#ffffff'><b>38%</b></font>", ParagraphStyle('SB3', alignment=1)),
         Paragraph("<font size=18 color='#ffffff'><b>BOTTOM 30%</b></font>", ParagraphStyle('SB4', alignment=1))]
    ]

    score_table = Table(score_data, colWidths=[3.7*inch, 3.7*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), PRIMARY),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 15))

    # The Google 23% Stat Box
    stat_data = [[
        Paragraph(
            "<font size=12 color='#D32F2F'><b>THE COST OF MIXED SIGNALS: +23% CLICK OPPORTUNITY</b></font><br/><br/>"
            "According to Google search data, local businesses that resolve Name, Address, and Phone (NAP) "
            "inconsistencies and establish total data consensus experience an average <b>+23% increase in customer clicks</b>.<br/><br/>"
            "Right now, 62% of major platforms have conflicting details on your business, causing search engines and AI to hesitate and favor your direct Highway 248 competitors.",
            body_style
        )
    ]]

    stat_table = Table(stat_data, colWidths=[7.4*inch])
    stat_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFEBEE")),
        ('BOX', (0,0), (-1,-1), 1.5, ACCENT_RED),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(stat_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Critical Foundation Risks Detected:", h2_style))
    story.append(Paragraph("* <b>The Ghost Factor:</b> Unverified or completely missing profiles on core map networks.", body_style))
    story.append(Paragraph("* <b>The Fragment Penalty:</b> Address conflicts ('Hwy' vs 'Highway' vs missing suite tags) diluting location authority.", body_style))
    story.append(Paragraph("* <b>The Broken Pipeline:</b> Inconsistent phone/hours sending AI search clients to competitors.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: THE REAL-TIME DATA DISCREPANCY MATRIX
    # =========================================================================

    story.append(Paragraph("REAL-TIME DATA DISCREPANCY MATRIX", title_style))
    story.append(Paragraph("Direct comparison of your official data versus live public listings:", subtitle_style))

    matrix_data = [
        ["Platform", "Business Name", "Address", "Phone", "Status"],
        ["Target Truth", biz_name, "123 Main St, Ste 100", "(555) 867-5309", "Verified Target"],
        ["Google Maps", biz_name, "123 Main Street", "(555) 867-5309", "Minor Mismatch"],
        ["Apple Maps", f"{biz_name} LLC", "123 Main St (No Suite)", "(555) 867-5309", "Critical Mismatch"],
        ["Yelp", f"{biz_name} &amp; Drain", "123 Main St, Ste 100", "(555) 123-4567", "Old Number"],
        ["Bing Places", "Not Found", "Not Found", "Not Found", "Missing Profile"],
        ["Facebook", biz_name, "123 Main St, Ste 100", "(555) 867-5309", "Unsynced Hours"]
    ]

    matrix_table = Table(matrix_data, colWidths=[1.1*inch, 1.6*inch, 2.1*inch, 1.3*inch, 1.3*inch])
    matrix_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT])
    ]))
    story.append(matrix_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Why This Matrix Matters", h2_style))
    story.append(Paragraph(
        "When search engines process your listing, they crawl all these sources simultaneously. "
        "If Apple Maps lacks your suite number and Yelp lists an outdated tracking line, algorithms classify "
        "your business as 'high-risk' and default to competitors with 100% clean data consensus.",
        body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: THE AI & REVIEWS GAP
    # =========================================================================

    story.append(Paragraph("AI READINESS &amp; REPUTATION GAP", title_style))
    story.append(Paragraph("How ChatGPT, Gemini, &amp; Apple Intelligence evaluate your business:", subtitle_style))

    ai_box = [[
        Paragraph(
            "<b>AI READINESS STATUS: HIGH RISK</b><br/><br/>"
            "Generative AI tools recommend local businesses based on <i>Data Consensus</i>. "
            "Because your directories display conflicting hours and phone records, AI search models "
            "assign a low confidence rating to your listing, actively suppressing your business in conversational queries.",
            body_style
        )
    ]]

    ai_table = Table(ai_box, colWidths=[7.4*inch])
    ai_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFF8E1")),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#FFA000")),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(ai_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Reputation Keyword Engine (Tier 2 Upgrade Preview)", h2_style))
    story.append(Paragraph(
        "Unanswered reviews harm map rankings. Our automated AI engine replies to 100% of your reviews, "
        "injecting critical service and location keywords directly into every response:",
        body_style
    ))
    story.append(Spacer(1, 5))

    reply_example = [
        [Paragraph("<b>Sample AI Keyword-Optimized Reply:</b>", ParagraphStyle('RE1', fontName='Helvetica-Bold', fontSize=10, textColor=PRIMARY))],
        [Paragraph(
            "<i>\"Thanks for the review, John! We were happy to handle your <b>emergency pipe repair</b> off "
            "<b>Highway 248</b>. Keeping our <b>Branson</b> community taken care of is always our priority!\"</i>",
            body_style
        )]
    ]

    reply_table = Table(reply_example, colWidths=[7.4*inch])
    reply_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#DDDDDD")),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(reply_table)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: THE SOLUTIONS ROADMAP & INFO NODE OFFER
    # =========================================================================

    story.append(Paragraph("THE 48-HOUR RECOVERY PLAN", title_style))
    story.append(Paragraph("Build on Bedrock, Not Sand - Zero Hassle, Maximum Signal Confidence", subtitle_style))

    offer_box = [[
        Paragraph(
            "<font size=13 color='#004488'><b>THE LOCKED INFO NODE SOLUTION - $249 SETUP</b></font><br/><br/>"
            "You don't need to spend thousands of dollars on complex websites or monthly agency retainers to rank.<br/><br/>"
            "<b>1. Deploy Your Single Info Node:</b> We build a lightning-fast single-page node that acts as your sealed Source of Truth for AI and Google.<br/>"
            "<b>2. Force Data Synergy:</b> We syndicate your exact Name, Address, and Phone out across Google, Apple Maps, Facebook, and Angi.<br/>"
            "<b>3. Lock &amp; Monitor ($25/mo):</b> We actively defend your web footprint so scrapers or bad directories never corrupt your data again.",
            body_style
        )
    ]]

    offer_table = Table(offer_box, colWidths=[7.4*inch])
    offer_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#E3F2FD")),
        ('BOX', (0,0), (-1,-1), 1.5, PRIMARY),
        ('PADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(offer_table)
    story.append(Spacer(1, 25))

    story.append(Paragraph("Summary Offer Tiers", h2_style))

    tier_data = [
        ["Package", "Includes", "Pricing"],
        ["Foundation Node", "1-Page Sealed Info Node + Core Data Sync + 24/7 Monitoring", "$249 Setup + $25/mo"],
        ["Growth Node", "Foundation Package + AI Keyword Review Engine + Reputation Shield", "$249 Setup + $79/mo"]
    ]

    tier_table = Table(tier_data, colWidths=[1.5*inch, 4.4*inch, 1.5*inch])
    tier_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PRIMARY),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(tier_table)
    story.append(Spacer(1, 30))

    story.append(Paragraph("Ready to claim your +23% click boost? Let's lock your data today.", callout_style))

    # Build Document
    doc.build(story)
    print(f"Generated Audit PDF: {filename}")


if __name__ == "__main__":
    build_pdf()
