import os
import glob
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

artifact_dir = r"C:\Users\adity\.gemini\antigravity-ide\brain\b12b794c-36eb-4fcb-a0e9-c9499d9acc18"
out_mp4 = os.path.join(artifact_dir, "agentic_diligence_demo.mp4")
out_webp = os.path.join(artifact_dir, "agentic_diligence_demo_animated.webp")

# Chapter definitions with timing and screenshot mapping
scenes = [
    {
        "img": "step1_loaded_1791124804930.png",
        "chapter": "01 / OVERVIEW",
        "title": "Agentic Diligence: The AI Audit Cockpit",
        "subtitle": "Eliminating the 'AI Facade': Auditing runtime autonomy, economics, and IP defensibility.",
        "badge": "EXECUTIVE COCKPIT",
        "badge_color": (34, 197, 94), # green
        "duration_sec": 8
    },
    {
        "img": "step2_audit_run_1791124830685.png",
        "chapter": "02 / RUNTIME TELEMETRY",
        "title": "Deterministic Telemetry Ingestion",
        "subtitle": "500 live traces analyzed: Autonomy, Unit Economics, Cost Spikes, and Single Vendor Risk.",
        "badge": "TELEMETRY INGESTION",
        "badge_color": (59, 130, 246), # blue
        "duration_sec": 8
    },
    {
        "img": "step4_tab1_claims_1791125073341.png",
        "chapter": "03 / ENGINE 1: CLAIMS VERIFIER",
        "title": "Pitch Deck Claims vs. Reality Check",
        "subtitle": "Claimed 95% Autonomy -> CONTRADICTED: Real data proves 24.4% Human Intervention Rate (HIR).",
        "badge": "CONTRADICTED CLAIM",
        "badge_color": (239, 68, 68), # red
        "duration_sec": 9
    },
    {
        "img": "step5_tab2_aibom_1791125121194.png",
        "chapter": "04 / ENGINE 5: AIBOM & SPOF",
        "title": "AI Bill of Materials (CycloneDX 1.6)",
        "subtitle": "Itemizing models & tools: 98% vendor lock-in to OpenAI flagged as Critical SPOF.",
        "badge": "98% VENDOR CONCENTRATION",
        "badge_color": (245, 158, 11), # amber
        "duration_sec": 8
    },
    {
        "img": "step6_tab3_cascades_1791125203519.png",
        "chapter": "05 / ENGINE 4: FAILURE CASCADES",
        "title": "System Outages & Cost Multiplication",
        "subtitle": "When external CRM/DB fails, retry loops cause a 2.19x cost multiplier and +2.1s latency spike.",
        "badge": "2.19x ERROR SPIKE",
        "badge_color": (239, 68, 68), # red
        "duration_sec": 8
    },
    {
        "img": "step7_tab6_toolrisk_1791125266646.png",
        "chapter": "06 / ENGINE 7: TOOL BLAST RADIUS",
        "title": "Privilege Tiers & Security Sandboxing",
        "subtitle": "Critical Risk: Shell commands and database writes executed without human supervision gates.",
        "badge": "CRITICAL RISK PERMISSIONS",
        "badge_color": (239, 68, 68), # red
        "duration_sec": 8
    },
    {
        "img": "step8_tab7_compare_1791125334053.png",
        "chapter": "07 / ENGINE 8: TARGET COMPARISON",
        "title": "Head-to-Head Diligence Comparison",
        "subtitle": "Comparing AcmeAI vs Company B: Automated dimension scoring for Autonomy, Economics & Safety.",
        "badge": "ACQUISITION BENCHMARK",
        "badge_color": (59, 130, 246), # blue
        "duration_sec": 8
    },
    {
        "img": "step8_tab7_matrix_1791125370393.png",
        "chapter": "08 / ENGINE 8: COMPARISON MATRIX",
        "title": "Granular Multi-Dimension Scoring",
        "subtitle": "Crowns explicit winners: Unit Economics, Architectural Resilience, and Autonomy.",
        "badge": "DIMENSION WINNERS",
        "badge_color": (168, 85, 247), # purple
        "duration_sec": 8
    },
    {
        "img": "step9_tab8_defensibility_1791125445605.png",
        "chapter": "09 / ENGINE 9: MOAT VS. WRAPPER",
        "title": "Defensibility & Cloning Barrier",
        "subtitle": "Moat Score: 70.3/100. Cloning Barrier: Replicating architecture requires 10 months and $420k.",
        "badge": "MOAT SCORE: 70.3/100",
        "badge_color": (34, 197, 94), # green
        "duration_sec": 9
    },
    {
        "img": "step10_tab9_stresstest_1791125644075.png",
        "chapter": "10 / ENGINE 10: WHAT-IF SIMULATOR",
        "title": "Financial Stress Testing & Gross Margins",
        "subtitle": "Live sensitivity sliders: Token cost surges and $35/hr human review fees expose margin risks.",
        "badge": "MARGIN SENSITIVITY",
        "badge_color": (245, 158, 11), # amber
        "duration_sec": 9
    },
    {
        "img": "step11_tab10_memo_1791125702282.png",
        "chapter": "11 / INVESTMENT COMMITTEE MEMO",
        "title": "Deal Verdict & 100-Day Playbook",
        "subtitle": "Recommendation: CONDITIONAL_REMEDIATION_REQUIRED with prioritized P0-P3 technical milestones.",
        "badge": "CONDITIONAL APPROVAL",
        "badge_color": (245, 158, 11), # amber
        "duration_sec": 9
    },
    {
        "img": "step12_download_dropdown_1791125774747.png",
        "chapter": "12 / CRYPTOGRAPHIC DIGITAL SEAL",
        "title": "Tamper-Proof Audit Package & Export",
        "subtitle": "SHA-256 chain-of-custody bundling CycloneDX AIBOM, IC Memo, and official PDF report.",
        "badge": "CRYPTOGRAPHIC SHA-256",
        "badge_color": (34, 197, 94), # green
        "duration_sec": 8
    }
]

print("Starting video composition...")
width, height = 1920, 1080
fps = 15

# Total duration calculation
total_duration_sec = sum(s["duration_sec"] for s in scenes)
total_frames = total_duration_sec * fps
print(f"Total video length: {total_duration_sec}s ({total_frames} frames) at {fps} fps")

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
video_writer = cv2.VideoWriter(out_mp4, fourcc, fps, (width, height))

# We will also keep animated gif/webp frames (sampled at 1 fps for compact size)
webp_frames = []

current_frame_idx = 0

for s_idx, scene in enumerate(scenes):
    img_path = os.path.join(artifact_dir, scene["img"])
    if not os.path.exists(img_path):
        print("Missing img:", img_path)
        continue
    
    src_img = Image.open(img_path).convert("RGB")
    num_frames = scene["duration_sec"] * fps
    
    # Calculate dimensions to fit screenshot in center-top
    header_h = 80
    hud_h = 160
    content_w = width - 40
    content_h = height - header_h - hud_h - 20
    
    # Resize screenshot preserving aspect ratio
    src_w, src_h = src_img.size
    ratio = min(content_w / src_w, content_h / src_h)
    new_w = int(src_w * ratio)
    new_h = int(src_h * ratio)
    resized_shot = src_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Base background canvas
    base_canvas = Image.new("RGB", (width, height), (13, 17, 23)) # dark slate
    draw = ImageDraw.Draw(base_canvas)
    
    # Paste screenshot centered in content area
    paste_x = (width - new_w) // 2
    paste_y = header_h + (content_h - new_h) // 2
    
    # Screenshot border / shadow card
    draw.rectangle([paste_x - 3, paste_y - 3, paste_x + new_w + 3, paste_y + new_h + 3], outline=(48, 54, 61), width=2)
    base_canvas.paste(resized_shot, (paste_x, paste_y))
    
    # Top Header Bar
    draw.rectangle([0, 0, width, header_h], fill=(22, 27, 34))
    draw.line([0, header_h, width, header_h], fill=(48, 54, 61), width=1)
    
    # Header Branding & Badges
    try:
        font_title = ImageFont.truetype("arialbd.ttf", 26)
        font_sub = ImageFont.truetype("arial.ttf", 18)
        font_badge = ImageFont.truetype("arialbd.ttf", 15)
        font_hud_title = ImageFont.truetype("arialbd.ttf", 28)
        font_hud_sub = ImageFont.truetype("arial.ttf", 20)
    except:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_badge = font_title
        font_hud_title = font_title
        font_hud_sub = font_title

    # Header text
    draw.text((30, 16), "AGENTIC DILIGENCE", fill=(255, 255, 255), font=font_title)
    draw.text((330, 22), "|   Standardized AI Due Diligence Platform", fill=(139, 148, 158), font=font_sub)
    
    # Top Right Chapter Indicator
    ch_text = scene["chapter"]
    draw.rectangle([width - 320, 18, width - 30, 58], fill=(33, 38, 45), outline=(56, 139, 253), width=1)
    draw.text((width - 305, 26), ch_text, fill=(88, 166, 255), font=font_badge)
    
    # Bottom HUD Bar
    hud_y = height - hud_h
    draw.rectangle([0, hud_y, width, height], fill=(22, 27, 34))
    draw.line([0, hud_y, width, hud_y], fill=(48, 54, 61), width=1)
    
    # Badge Pill in HUD
    badge_text = scene["badge"]
    badge_col = scene["badge_color"]
    # Draw badge pill
    draw.rectangle([30, hud_y + 24, 30 + len(badge_text)*11 + 20, hud_y + 54], fill=(badge_col[0]//4, badge_col[1]//4, badge_col[2]//4), outline=badge_col, width=1)
    draw.text((40, hud_y + 30), badge_text, fill=badge_col, font=font_badge)
    
    # HUD Title and Subtitle
    draw.text((30, hud_y + 66), scene["title"], fill=(240, 246, 252), font=font_hud_title)
    draw.text((30, hud_y + 104), scene["subtitle"], fill=(139, 148, 158), font=font_hud_sub)
    
    # Convert PIL base canvas to OpenCV frame template
    frame_template = np.array(base_canvas)
    frame_template = cv2.cvtColor(frame_template, cv2.COLOR_RGB2BGR)
    
    for f in range(num_frames):
        current_frame_idx += 1
        frame = frame_template.copy()
        
        # Animated Progress Bar at bottom (height: 6px)
        progress = current_frame_idx / total_frames
        bar_w = int(width * progress)
        cv2.rectangle(frame, (0, height - 6), (bar_w, height), (255, 100, 30), -1)
        
        # Subtly pulse the badge border during display
        pulse = int(20 * np.sin(f * 0.15))
        
        video_writer.write(frame)
        
        # Sample 1 frame per scene for animated webp
        if f == num_frames // 2:
            rgb_f = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            webp_frames.append(Image.fromarray(rgb_f).resize((960, 540), Image.Resampling.BILINEAR))

video_writer.release()
print(f"Demo video MP4 generated: {out_mp4} ({round(os.path.getsize(out_mp4)/(1024*1024), 2)} MB)")

# Save animated WebP
if webp_frames:
    webp_frames[0].save(
        out_webp,
        save_all=True,
        append_images=webp_frames[1:],
        duration=[s["duration_sec"] * 1000 for s in scenes],
        loop=0
    )
    print(f"Animated demo WebP generated: {out_webp} ({round(os.path.getsize(out_webp)/(1024*1024), 2)} MB)")
