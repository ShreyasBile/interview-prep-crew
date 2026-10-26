"""Sample resumes, a job description, and tiny PDF/DOCX builders for tests."""

import io
import zipfile

GOOD_RESUME = """Aarav Sharma
aarav.sharma@example.com | +91 98765 43210 | linkedin.com/in/aaravsharma | github.com/aaravsharma

SUMMARY
Software engineer with two years of experience building REST APIs and data pipelines in Python and Java. Strong in data structures, algorithms and cloud deployment.

EDUCATION
B.Tech in Computer Science, Pune Institute of Technology, 2020 - 2024
CGPA 8.6 / 10

SKILLS
Python, Java, SQL, FastAPI, Spring Boot, Docker, Kubernetes, AWS, Git, PostgreSQL, Redis, CI/CD, Agile

EXPERIENCE
Software Engineer, Nimbus Labs, Jul 2024 - Present
• Built 12 REST API endpoints in FastAPI serving 40,000 daily requests with 99.9% uptime
• Reduced report generation time by 65% by redesigning PostgreSQL queries and adding Redis caching
• Automated deployments with Docker and GitHub Actions, cutting release time from 2 hours to 15 minutes
• Led a team of 4 interns to deliver an internal analytics dashboard in 6 weeks
• Mentored 3 junior developers on code reviews and unit testing with pytest
• Optimized Kubernetes resource limits, saving 22% of monthly cloud spend
• Designed a retry and alerting layer that reduced failed jobs by 80%

Software Engineering Intern, Orbit Systems, May 2023 - Jul 2023
• Developed a Java Spring Boot service that processed 5,000 orders per day
• Improved test coverage from 40% to 85% by writing 120 unit tests
• Documented 8 microservices to speed up onboarding for new teammates
• Implemented input validation that blocked 300 malformed requests per week

PROJECTS
Smart Campus Assistant
• Designed a chatbot using Python and machine learning that answered 500 student queries per week
• Deployed the application on AWS with Kubernetes and monitored it with Grafana
• Created a dataset of 2,000 labelled questions and improved accuracy from 71% to 89%
Expense Tracker
• Built a React and Node.js web app used by 150 classmates to split shared costs
• Integrated UPI payment links and reduced manual reconciliation time by 50%

CERTIFICATIONS
AWS Certified Cloud Practitioner, 2024
Google Data Analytics Certificate, 2023
"""

POOR_RESUME = (
    "I am a hard working person. I am responsible for many things and worked on various projects. "
    "My duties included helping with tasks and I was involved in team activities. I like to learn new things "
    "and my goal is to get a job in a good company where I can grow my career and help the company succeed "
    "in the future. I am a quick learner and a team player who is always ready to take on new challenges."
)

JOB_DESCRIPTION = (
    "We are hiring a Backend Engineer. You will build REST APIs in Python and FastAPI, design PostgreSQL "
    "schemas, and deploy services with Docker and Kubernetes on AWS. Experience with CI/CD, Redis caching, "
    "unit testing and Agile teams is required. Kafka and GraphQL are a plus."
)


def make_pdf(lines: list[str]) -> bytes:
    """A minimal one-page PDF whose text can be extracted."""
    safe = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream = "BT /F1 11 Tf 50 750 Td 14 TL " + " ".join(f"({line}) '" for line in safe) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_docx(paragraphs: list[tuple[str, bool]]) -> bytes:
    """A minimal .docx; each paragraph is (text, is_list_item)."""
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = ""
    for text, is_list in paragraphs:
        props = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>' if is_list else ""
        body += f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()
