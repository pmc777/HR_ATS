# HR ATS – Simple Applicant Tracking System

A lightweight, desktop-based **Applicant Tracking System** built with Python and Tkinter. Designed for small teams, recruiters, or HR professionals who want a simple, offline-first tool to manage candidates without relying on expensive cloud platforms.

https://github.com/yourusername/hr-ats

![HR ATS Screenshot]
<img width="1595" height="1012" alt="image" src="https://github.com/user-attachments/assets/6e3c6576-6fad-4916-a2d0-5c5bca850410" />

## Features

- **Dashboard** – Overview of total applicants, status breakdown, upcoming interviews, recently added candidates
- **Applicants Management**
  - Add new applicants manually
  - Import candidates from CSV files (e.g., from job boards)
  - Update application status (Applied → Screening → Interview → Offer → Hired / Rejected)
  - Schedule interviews (date field)
  - Send templated emails via mailto links
  - Generate basic offer letter PDFs
  - Delete applicants (with confirmation)
- **Email Templates**
  - Create, edit, and delete reusable email templates
  - Use placeholders: `{name}`, `{job}`
- **Settings**
  - Configure default status for new applicants
  - Future integration placeholders for job boards (Indeed, ZipRecruiter, LinkedIn, Monster)
- **Offline-first** – Everything stored in a local SQLite database
- No login required (single-user desktop app)

## Screenshots

### Dashboard
![Dashboard]<img width="1595" height="1012" alt="image" src="https://github.com/user-attachments/assets/c60605ea-b821-4022-98a4-0014c6633cc6" />


### Applicants List
![Applicants]<img width="1578" height="1012" alt="image" src="https://github.com/user-attachments/assets/3cc9ef36-4af6-49b4-a222-53243afe75de" />


### Email Templates
![Templates]<img width="1591" height="1007" alt="image" src="https://github.com/user-attachments/assets/dec0ec86-63a7-4bb9-a45d-fde27fd6e201" />

## Tech Stack

- **Python** 3.8+
- **Tkinter** (standard GUI library)
- **SQLite** (local database via sqlite3)
- **ReportLab** (PDF generation for offer letters)
- **CSV** module (for importing candidates)

## Installation

1. **Clone the repository**

```bash
git clone https://github.com/yourusername/hr-ats.git
cd hr-ats
