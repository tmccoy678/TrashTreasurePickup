# Supplemental audit of the DobeWorks reference PDF

Audit date: 2026-09-11. Scope: all **44 works** in the seven-page historical reference PDF, in printed order. This is a bibliographic and source-access audit, not a claim that all 44 complete works were read or that DW/DEGS complies with them. The original PDF was read, not rewritten.

Source: the preserved historical `dobeworks-apa-references.pdf` in the DobeWorks and DEGS draft repositories. SHA-256: `fc6f090f2f9a937f6ab6d62cc505611969a18e00dde1ef026f5f981ad150c557`. Preserve that artifact unchanged; apply any accepted corrections to a dated supplement or revised figure bibliography.

Evidence labels: **Matched** means the cited identity and material metadata were confirmed from the publisher, originating organization, author archive, or source repository. **Correction** identifies a concrete title, credit, or link adjustment. **Partial** means some fields or access remain unresolved. Bibliographic registration records are identified explicitly where a publisher page could not be opened. Historical “Retrieved August 31, 2026” dates cannot be independently re-created by this audit; retain them as historical claims rather than replacing them with today's date.

## Findings that affect reuse

- The CUDA citation names release 13.3 but the unversioned link now serves **13.4**. Use the verified **13.3.0 archive** when discussing the historical source. This is link drift, not evidence that the original reference was wrong when written.
- CISA's secure-by-design guidance is jointly authored by **18 organizations**. Sole CISA credit understates the document's credited authorship.
- The pinned Microsoft source is titled **ISE Engineering Fundamentals Customer/Partner Engineering Playbook** in its README; its site configuration uses **Engineering Fundamentals Playbook**. “Code with engineering playbook” is the repository slug, not either formal title.
- The DoD Responsible AI Pathway cover names the **DoD Responsible AI Working Council** as preparer. CDAO's hosting and implementation role should not erase that credit.
- MIL-STD-882E is a **Department of Defense** standard, prepared by **Air Force–40**, with DLA hosting the catalog. Avoid treating DLA hosting as authorship.
- The revised NASA entry now explicitly selects **NTRS item 20170001761**, the first handbook source in the canonical source register, with its three named authors and **2017** publication year. Its report number retains **2016**. The NTRS attachment and NASA landing-page designed PDF are different files; the choice and both hashes are documented below.
- Apple documentation, IBM z/OS documentation, and the two MIT ELO pages have access limitations described below. Their failure to load here is not proof that the cited work does not exist.

## Complete 44-entry audit

| # | Printed work | Status and exact finding | Primary evidence / accessible route |
|---|---|---|---|
| 1 | Apple — Privacy governance (n.d.) | **Matched.** Official page title and Apple identity match; no publication date was exposed. Historical retrieval date unverified. | [Apple privacy governance](https://www.apple.com/legal/privacy/en-ww/governance/) — readable HTML. |
| 2 | Apple teams — Private Cloud Compute: A new frontier for AI privacy in the cloud (2024-06-10) | **Matched.** Date, title, and five-team byline match. Full team labels include SEAR, Core OS, ASE, and AIML acronyms; omission of those explanatory acronyms does not change the identified teams. | [Original Apple article](https://security.apple.com/blog/private-cloud-compute/) — readable article and byline. |
| 3 | Same Apple teams — Expanding Private Cloud Compute (2026-06-08) | **Matched.** Official article confirms title, June 8, 2026, and same teams. | [Original Apple article](https://security.apple.com/blog/expanding-pcc/) — readable article and byline. |
| 4 | Apple Security Research — Documentation (n.d.) | **Partial.** URL resolves to an Apple page titled Documentation, but retrieval exposes only a JavaScript-required message. Body, exact documentation edition, and undated authorship were not independently checked. | [Apple PCC documentation](https://security.apple.com/documentation/private-cloud-compute/) — JavaScript/browser access needed; do not claim full-text verification. |
| 5 | Barbacci, Ellison, Lattanze, Stafford, Weinstock, & Wood — Quality attribute workshops, third edition (2003) | **Matched.** All six authors, title, report CMU/SEI-2003-TR-016, and DOI `10.1184/R1/6582656.v1` confirmed. Official landing page gives October 1, 2003; year-only book/report citation is sufficient. | [SEI publication record](https://sei.cmu.edu/library/quality-attribute-workshops-qaws-third-edition/) — authoritative metadata and PDF link; DOI is explicitly printed there. |
| 6 | Booth, Ogata, Kent, Souppaya, & Dodson — SSDF version 1.2 (2025-12-17) | **Matched.** Five authors in that order, date, NIST SP 800-218 Rev. 1, title, and DOI `10.6028/NIST.SP.800-218r1.ipd` confirmed. **Initial Public Draft**, not a final standard; closed comment period does not make it final. | [NIST IPD record](https://csrc.nist.gov/pubs/sp/800/218/r1/ipd) — metadata, draft status, download and DOI. |
| 7 | Booth, Souppaya, Vassilev, Ogata, Stanley, & Scarfone — Generative AI SSDF community profile (2024) | **Matched.** Six authors/order, title, NIST SP 800-218A, July 2024, and DOI `10.6028/NIST.SP.800-218A` confirmed from cover and front matter. The cover's title is preferable to the slightly inconsistent suggested-citation sentence inside the report. | [NIST original PDF](https://doi.org/10.6028/NIST.SP.800-218A) — front matter inspected, not a full substantive review. |
| 8 | CISA — Shifting the balance of cybersecurity risk (2023, October; refined/expanded) | **Correction: credit.** Title and October 2023 revision match. Document credits CISA, NSA, FBI, ACSC, CCCS, CERT NZ, NCSC-NZ, NCSC-UK, BSI, NCSC-NL, NCSC-NO, NÚKIB, INCD, KISA, NISC-JP, JPCERT/CC, CSA, and CSIRTAMERICAS. Credit the joint organizations in the revised reference/credit note; retain CISA as host. “Refined and expanded” is a useful edition description, not a separate numbered edition. | [Original CISA PDF](https://www.cisa.gov/sites/default/files/2023-10/Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-Approaches-for-Secure-by-Design-Software.pdf) — downloaded directly after web-tool failure; cover, organizational credits, and October-update text inspected. |
| 9 | de Weck — Fundamentals of systems engineering (2015) | **Matched.** MIT OCW names Prof. Olivier de Weck as instructor and Fall 2015 as the course offering. Course 16.842 and title match. | [MIT OCW course](https://ocw.mit.edu/courses/16-842-fundamentals-of-systems-engineering-fall-2015/) — public course metadata; not every lecture reviewed. |
| 10 | Dijkstra — Notes on structured programming (1970; second edition) | **Matched.** Author archive transcript explicitly identifies EWD249, T.H. Report 70-WSK-03, second edition April 1970. The internal August 1969 date refers to the earlier text; it does not invalidate the 1970 edition citation. | [University of Texas Dijkstra archive](https://www.cs.utexas.edu/~EWD/transcriptions/EWD02xx/EWD249/EWD249.html) — title pages and transcript readable. |
| 11 | Grunbok & Cole — Security in development: The IBM Secure Engineering Framework (2018) | **Matched.** Warren Grunbok and Marie Cole, December 17, 2018, REDP-4641-01. ISBN 9780738457178 confirmed on publisher page. | [IBM Redbooks record](https://www.redbooks.ibm.com/abstracts/redp4641.html) — metadata and official PDF/EPUB links. |
| 12 | Hirshorn, Voss, & Bromley — NASA systems engineering handbook (printed as 2016; Rev. 2) | **Corrected after explicit source selection.** Revised edition selects NTRS item 20170001761, first in canonical source register: Hirshorn, Voss, & Bromley **(2017)**, report NASA/SP-2016-6105 Rev. 2. NTRS publication date is February 17, 2017. Current attachment has 356 PDF pages; the landing-page designed file has 297. They are not treated as identical. Historical byte identity remains unknown. | [Selected NTRS record](https://ntrs.nasa.gov/citations/20170001761); [official attachment](https://ntrs.nasa.gov/api/citations/20170001761/downloads/20170001761.pdf); [NTRS metadata](https://ntrs.nasa.gov/api/citations/20170001761). |
| 13 | IBM — z/OS 3.2 system integrity (n.d.) | **Partial.** Exact cited URL returns HTTP 403 through both retrieval routes. z/OS version, precise heading, and body cannot be called verified in this audit. No replacement version was substituted. | [Cited IBM documentation](https://www.ibm.com/docs/en/zos/3.2.0?topic=aapmss-system-integrity) — access-limited here. |
| 14 | IBM Policy — IBM artificial intelligence pillars (n.d.-a) | **Matched.** Main heading matches; no page date exposed. Institutional author IBM / IBM Policy is consistent with the source site. | [IBM pillars](https://www.ibm.com/policy/blog/ibm-artificial-intelligence-pillars) — readable HTML. |
| 15 | IBM Policy — IBM's principles for trust and transparency (n.d.-b) | **Matched.** Main heading matches the reference. Browser metadata inserts “Data,” but the displayed heading does not; retain the displayed heading. No date exposed. | [IBM trust principles](https://www.ibm.com/policy/blog/trust-principles) — readable HTML. |
| 16 | ISO/IEC/IEEE 15288:2023 — System life cycle processes (edition 2) | **Matched.** Title, organizations, edition 2, May 2023, and standard number confirmed. | [ISO official catalog](https://www.iso.org/standard/81702.html) — public metadata/abstract; complete paid standard not inspected. |
| 17 | ISO/IEC/IEEE 12207:2026 — Software life cycle processes (edition 2) | **Matched.** Published edition 2, April 2026, exact standard/title confirmed. It is not a draft in this catalog record. | [ISO official catalog](https://www.iso.org/standard/90219.html) — public metadata/abstract; complete paid standard not inspected. |
| 18 | Lockheed Martin — Software Factory continues to expand (2020-08-24) | **Matched.** Exact title and August 24, 2020 match publisher HTML title and embedded `publishDate`. Browser research fetch was denied; direct public-page retrieval succeeded. | [Lockheed Martin original article](https://www.lockheedmartin.com/en-us/news/features/2020/lockheed-martin-software-factory-continues-expand-company-accelerates-software-development-capabilities.html). |
| 19 | Lockheed Martin Skunk Works — The Skunk Works legacy (n.d.) | **Partial / metadata refinement.** Publisher title is The Skunk Works® Legacy; current descriptive heading also adds “Developing the US's First Fighter Jet.” HTML `publishDate` is September 26, 2023, but this may describe page publication/migration, not the original historical essay. Preserve n.d. unless citing that current page revision explicitly; record the metadata date separately. | [Lockheed Martin source](https://www.lockheedmartin.com/en-us/who-we-are/business-areas/aeronautics/skunkworks/skunk-works-origin-story.html) — direct HTML inspected. |
| 20 | Microsoft — Responsible AI Standard v2: General requirements (June 2022) | **Matched.** Cover confirms Microsoft, version 2, general requirements, June 2022, external release. | [Microsoft original PDF](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Microsoft-Responsible-AI-Standard-General-Requirements.pdf) — cover/front matter inspected. |
| 21 | Microsoft — Security Development Lifecycle (2025-09-29) | **Matched.** Exact title and “Last updated on 2025-09-29” visible. This is an update date, not evidence that SDL originated in 2025. | [Microsoft Learn source](https://learn.microsoft.com/en-us/compliance/assurance/assurance-microsoft-security-development-lifecycle) — article readable despite generic authorization banner. |
| 22 | Microsoft ISE — Code with engineering playbook (pinned) | **Correction: formal title.** Pin `016770e43d8a75be87b98c000c049f07c4a6e6f8` exists. README title is ISE Engineering Fundamentals Customer/Partner Engineering Playbook; site title is Engineering Fundamentals Playbook, author Microsoft ISE. Commit date September 26, 2025 is a snapshot date, not proof every chapter was authored then. Preserve pin and n.d. unless explicitly dating the snapshot. | [Pinned README](https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/README.md); [pinned site metadata](https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/mkdocs.yml). |
| 23 | MIT ELO — About the Office / What is experiential learning? (n.d.-a) | **Partial.** Cited URL returned 502 in browser research and closed the direct connection. Exact heading/date/body unverified. Other MIT pages confirm the ELO domain, but do not independently verify this particular work. | [Cited MIT ELO page](https://elo.mit.edu/about/) — retry in an ordinary browser when available. |
| 24 | MIT ELO — Best practices for experiential learning (n.d.-b) | **Partial.** Same access failure as #23. Do not substitute unrelated MIT mentoring advice while retaining this title. | [Cited MIT ELO page](https://elo.mit.edu/best-practices/) — currently unverified body/heading. |
| 25 | NASA OCE — Software engineering handbook (NASA-HDBK-2203, D/0; 2020-04-20) | **Matched.** NASA catalog confirms document number, version d, change 0, April 20, 2020, responsible Office of Chief Engineer. It describes a wiki-based handbook; the catalog date does not freeze all current wiki content. | [NASA standards record](https://standards.nasa.gov/standard/NASA/NASA-HDBK-2203) — full metadata readable. |
| 26 | NASA OCE — Software engineering requirements (NPR 7150.2D; 2022-03-08) | **Matched.** NODIS confirms title, version, responsible office, effective March 8, 2022. | [NODIS NPR 7150.2D](https://nodis3.gsfc.nasa.gov/displayDir.cfm?c=7150&s=2D&t=NPR) — metadata and chapters accessible. |
| 27 | NASA OCE — Systems engineering processes and requirements (NPR 7123.1D Change 2; 2023-07-05) | **Matched with date qualification.** NODIS confirms base effective date July 5, 2023 and current subject “Updated w/Change 2.” The audit did not retrieve the change log; do not describe July 5, 2023 as the separately verified date of Change 2. | [NODIS NPR 7123.1D](https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_) — metadata readable, change-log fetch failed. |
| 28 | NVIDIA — CUDA C++ best practices guide (release 13.3; n.d.) | **Correction: versioned link.** Current unversioned destination says 13.4; official archive confirms 13.3. Use archive URL when reusing this historical citation. No claim that DW/DEGS needs CUDA or tests NVIDIA hardware follows from this source. | [Verified CUDA 13.3 archive](https://docs.nvidia.com/cuda/archive/13.3.0/cuda-c-best-practices-guide/index.html). |
| 29 | NVIDIA — Sustainability report fiscal year 2025 (2025) | **Matched.** Cover/title, corporate author, copyright 2025, and approximately June 12, 2025 information date confirmed. Fiscal period ends January 26, 2025; fiscal year and publication year are distinct but both support this citation. | [NVIDIA original report](https://images.nvidia.com/aem-dam/Solutions/documents/NVIDIA-Sustainability-Report-Fiscal-Year-2025.pdf) — cover and report-about/copyright portions inspected. |
| 30 | NVIDIA — Security development lifecycle for NVIDIA AI Enterprise (2026-04-15) | **Matched.** Title and last-updated April 15, 2026 confirmed. The URL is a mutable latest white-paper chapter; retain date and record an archive/snapshot if exact historical text matters. | [NVIDIA official chapter](https://docs.nvidia.com/ai-enterprise/planning-resource/ai-enterprise-security-white-paper/latest/security-lifecycle.html). |
| 31 | OWASP Foundation — Application security verification standard 5.0.0 (2025-05-30) | **Matched; improve stability.** Official source release is tagged `v5.0.0_release`, published May 30, 2025. Avoid the automatically refreshed bleeding-edge release for a 5.0.0 citation. | [OWASP 5.0.0 release](https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release) — repository API metadata inspected; original website redirect failed. |
| 32 | Parnas — On the criteria to be used in decomposing systems into modules (1972) | **Matched registration metadata; publisher access limited.** D. L. Parnas, December 1972, Communications of the ACM 15(12), 1053–1058, DOI `10.1145/361598.361623`. ACM page fetch denied; ACM-deposited DOI registration metadata confirmed the fields. Full paper not read for this audit. | [ACM DOI](https://doi.org/10.1145/361598.361623); [publisher-deposited Crossref record](https://api.crossref.org/works/10.1145%2F361598.361623). |
| 33 | Saltzer, Reed, & Clark — End-to-end arguments in system design (1984) | **Matched registration metadata; publisher access limited.** Three authors/order, November 1984, ACM Transactions on Computer Systems 2(4), 277–288, DOI `10.1145/357401.357402` confirmed from ACM-deposited DOI metadata. Full paper not read for this audit. | [ACM DOI](https://doi.org/10.1145/357401.357402); [publisher-deposited Crossref record](https://api.crossref.org/works/10.1145/357401.357402). |
| 34 | SEBoK Editorial and Governing Boards — Guide to SEBoK v2.14 (2026) | **Matched version; attribution qualified.** Release page confirms May 18, 2026 and names both boards, editor-in-chief Nicole Hutchison, and managing editor Chris Hoffman. Treat the printed collective-author form as a descriptive credit, not a verified publisher-prescribed citation. Version page is release information, not a frozen copy of every linked article. | [SEBoK v2.14](https://sebokwiki.org/wiki/Version_2.14); [observed page revision](https://sebokwiki.org/w/index.php?title=Version_2.14&oldid=78836). |
| 35 | SLSA Community — SLSA specification v1.2 (2025-11-24) | **Matched.** Official specification is approved v1.2. Official announcement source dated November 24, 2025 names SLSA Community. | [SLSA v1.2](https://slsa.dev/spec/v1.2/); [official announcement source](https://github.com/slsa-framework/slsa/blob/main/www/_posts/2025-11-24-announce-slsa-v1.2.md). |
| 36 | Souppaya, Scarfone, & Dodson — SSDF version 1.1 (2022) | **Matched.** Three authors/order, NIST SP 800-218, title, February 2022 publication, DOI `10.6028/NIST.SP.800-218` confirmed. Distinguish this final version from #6's draft revision. | [NIST final record](https://csrc.nist.gov/pubs/sp/800/218/final). |
| 37 | Swift project — Swift evolution process (pinned; n.d.) | **Matched.** Commit `c8623621aacc8e3f364bb0f3cb07675177a1ec4e` exists (August 27, 2026); pinned `process.md` title matches. Swift project collective credit is appropriate; the merge committer is not the sole author of the document. | [Pinned process](https://github.com/swiftlang/swift-evolution/blob/c8623621aacc8e3f364bb0f3cb07675177a1ec4e/process.md). |
| 38 | DoD — Engineering of Defense Systems (DoDI 5000.88; 2020a-11-18) | **Matched.** Official PDF cover confirms number, title, effective November 18, 2020, originating OUSD(R&E). Lowercase `.pdf` route accessible where uppercase retrieval failed. | [Official DoDI 5000.88](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500088p.pdf) — cover inspected. |
| 39 | DoD — Operation of the Software Acquisition Pathway (DoDI 5000.87; 2020b-10-02) | **Matched.** Official PDF confirms number/title/date and originating OUSD(A&S). The 2020a/2020b title order in the original bibliography is consistent: Engineering precedes Operation. | [Official DoDI 5000.87](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500087p.pdf) — cover inspected. |
| 40 | DoD — Digital engineering (DoDI 5000.97; 2023-12-21) | **Matched.** Official cover confirms exact title, date, number, and OUSD(R&E). | [Official DoDI 5000.97](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500097p.PDF) — primary indexed cover text inspected. |
| 41 | DoD — Operational test and evaluation and live fire test and evaluation of AI-enabled and autonomous systems (DoDM 5000.101; 2024-12-09) | **Matched.** Official PDF title/date/number confirmed; 25-page PDF accessible using official version-query URL. This does not show that DW/DEGS underwent military operational testing. | [Official DoDM 5000.101](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodm/5000101p.PDF?ver=FfOR56lIK5S1LDFfSlYwYQ%3D%3D). |
| 42 | DoD CDAO — Responsible AI strategy and implementation pathway (June 2022) | **Correction: preparer credit / accessible URL.** Cover confirms June 2022 and title; it explicitly says prepared by DoD Responsible AI Working Council. Use U.S. Department of Defense, Responsible AI Working Council as credited preparer, or DoD as corporate author plus a clear preparer note. CDAO is a related implementation office, not the named preparer on this cover. | [Official DoD-hosted PDF](https://media.defense.gov/2022/Jun/22/2003022604/-1/-1/0/Department-of-Defense-Responsible-Artificial-Intelligence-Strategy-and-Implementation-Pathway.PDF) — cover readable; original ai.mil URL denied direct retrieval. |
| 43 | DoD, Defense Logistics Agency — System safety (MIL-STD-882E Change 1; 2023-09-27) | **Correction: distinguish host from author.** Official DLA-hosted cover confirms Department of Defense standard practice, number/change/title/date. Concluding material names preparing activity Air Force–40. Recommend U.S. Department of Defense as corporate author, DLA ASSIST as catalog host. Exact catalog fetch failed; official indexed PDF and concluding material confirm metadata. | [Persistent DLA catalog](https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027); [official DLA PDF inspected](https://quicksearch.dla.mil/Transient/411C31BE0E0C4F898EACDFE832107967.pdf). Transient link may expire; use catalog as the durable citation. |
| 44 | Walden, Shortell, Roedler, Delicado, Mornas, Yip, & Endler (Eds.) — INCOSE systems engineering handbook, fifth edition (2023) | **Matched core metadata; report identifier unresolved.** Wiley excerpt explicitly names all seven editors in printed order, subtitle, fifth edition, 2023, John Wiley & Sons Ltd. INCOSE verifies ISBN 978-1-119-81429-0. The additional identifier `INCOSE-TP-2003-002-05-2023` was not confirmed in accessible front matter; omit it from a corrected citation pending exact evidence. Preserve editor spelling Shortell; one INCOSE catalog page inconsistently says Shortall. | [Wiley primary excerpt](https://catalogimages.wiley.com/images/db/pdf/9781119814290.excerpt.pdf); [INCOSE handbook/editor page](https://www.incose.org/resources-publications/technical-publications/se-handbook/). Full book not inspected. |

## Supplemental credit for the new Sashiko-derived work

Chris Mason and Muchun Song are **not entries in these original 44 works**. Add them in the new code-provenance/figure references where their contributions are actually used, rather than altering the historical PDF or implying they authored the original DW/DEGS systems.

- Credit **The Sashiko Authors** for the Apache-2.0 project at [pinned Sashiko commit 39f6ce95c797bb40023247916a8b16d0f4aaf0da](https://github.com/sashiko-dev/sashiko/tree/39f6ce95c797bb40023247916a8b16d0f4aaf0da). The link target is the verified full commit; the correct full SHA is `39f6ce95c797bb40023247916a8b16d0f4aaf0da`.
- Credit **Muchun Song** for the upstream [dismissed-concern preservation commit](https://github.com/sashiko-dev/sashiko/commit/39ff1c4d4a9e6fef466dfade79d34617c28f6cda) and [concern conflict-resolution commit](https://github.com/sashiko-dev/sashiko/commit/522c14b7ac7461eecb2655c3d358afab4e5996b2). These are specific provenance claims; later refactors and contributions retain collective credit.
- Credit **Chris Mason** for [review-prompts at pinned commit 032284304f3bbad50e092fa870c5d810de324d9f](https://github.com/masoncl/review-prompts/tree/032284304f3bbad50e092fa870c5d810de324d9f), whose [MIT license](https://github.com/masoncl/review-prompts/blob/032284304f3bbad50e092fa870c5d810de324d9f/LICENSE) identifies his copyright. Do not attribute all present Sashiko Rust implementation to him.

The [DEGS draft attribution record](https://github.com/tmccoy678/draftdegs/blob/84f948be07bb083bb976d1a0474925ec2cb6bc89/CITATIONS.md) links the source identities, contribution credits, and adaptation limits. Repository access is required while this draft remains private. References give credit; required license/notice preservation belongs alongside copied or adapted code. These references do not imply endorsement, certification, or transfer of upstream ownership.

## Remaining verification limits

The outstanding source-access items are #4, #13, #23, and #24. Edition/citation details remain qualified for #19, #27, #34, and #44. NASA #12 is resolved for the explicitly selected NTRS edition; historical byte identity is not claimed. ACM metadata in #32–33 is confirmed through publisher-deposited registration records, not claimed as inspected full text. All other rows identify the actual evidence depth. No reference has been silently replaced with a different work; no DOI has been invented.

## Renderer records: revised references with explicit qualifications

The following records supply all 44 reference strings and stable IDs. They are APA-style editorial input, not a declaration that every unresolved field is final. Apply italic styling to work titles and journal names/volumes in the renderer. Keep each `status` and `note` available in the supplemental audit; do not relabel `partial_metadata` or `unresolved_source_access` as verified. #8 now expands all 18 corporate authors from the original report’s page 5. #12 selects the registered NTRS source explicitly and uses its 2017 publication year. #42 credits DoD corporately and names the Working Council in its note. #43 corrects the host/author conflation, which also changes #40/#43 year suffixes. The original numeric IDs preserve audit cross-references even if the revised bibliography is re-sorted alphabetically.

```json
[
  {
    "id": 1,
    "apa": "Apple. (n.d.). Privacy governance. Retrieved August 31, 2026, from https://www.apple.com/legal/privacy/en-ww/governance/",
    "url": "https://www.apple.com/legal/privacy/en-ww/governance/",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official page title and Apple identity match; no publication date was exposed. Historical retrieval date unverified.",
    "evidence_urls": [
      "https://www.apple.com/legal/privacy/en-ww/governance/"
    ]
  },
  {
    "id": 2,
    "apa": "Apple Security Engineering and Architecture, User Privacy, Core Operating Systems, Services Engineering, & Machine Learning and AI. (2024, June 10). Private Cloud Compute: A new frontier for AI privacy in the cloud. https://security.apple.com/blog/private-cloud-compute/",
    "url": "https://security.apple.com/blog/private-cloud-compute/",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Date, title, and five-team byline match. Full team labels include SEAR, Core OS, ASE, and AIML acronyms; omission of those explanatory acronyms does not change the identified teams.",
    "evidence_urls": [
      "https://security.apple.com/blog/private-cloud-compute/"
    ]
  },
  {
    "id": 3,
    "apa": "Apple Security Engineering and Architecture, User Privacy, Core Operating Systems, Services Engineering, & Machine Learning and AI. (2026, June 8). Expanding Private Cloud Compute. https://security.apple.com/blog/expanding-pcc/",
    "url": "https://security.apple.com/blog/expanding-pcc/",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official article confirms title, June 8, 2026, and same teams.",
    "evidence_urls": [
      "https://security.apple.com/blog/expanding-pcc/"
    ]
  },
  {
    "id": 4,
    "apa": "Apple Security Research. (n.d.). Documentation. Retrieved August 31, 2026, from https://security.apple.com/documentation/private-cloud-compute/",
    "url": "https://security.apple.com/documentation/private-cloud-compute/",
    "status": "unresolved_source_access",
    "note": "**Partial.** URL resolves to an Apple page titled Documentation, but retrieval exposes only a JavaScript-required message. Body, exact documentation edition, and undated authorship were not independently checked.",
    "evidence_urls": [
      "https://security.apple.com/documentation/private-cloud-compute/"
    ]
  },
  {
    "id": 5,
    "apa": "Barbacci, M. R., Ellison, R. J., Lattanze, A. J., Stafford, J. A., Weinstock, C., & Wood, W. (2003). Quality attribute workshops (QAWs), third edition (CMU/SEI-2003-TR-016). Software Engineering Institute, Carnegie Mellon University. https://doi.org/10.1184/R1/6582656.v1",
    "url": "https://doi.org/10.1184/R1/6582656.v1",
    "status": "primary_metadata_matched",
    "note": "**Matched.** All six authors, title, report CMU/SEI-2003-TR-016, and DOI `10.1184/R1/6582656.v1` confirmed. Official landing page gives October 1, 2003; year-only book/report citation is sufficient.",
    "evidence_urls": [
      "https://sei.cmu.edu/library/quality-attribute-workshops-qaws-third-edition/"
    ]
  },
  {
    "id": 6,
    "apa": "Booth, H., Ogata, M., Kent, K., Souppaya, M., & Dodson, D. (2025, December 17). Secure software development framework (SSDF) version 1.2: Recommendations for mitigating the risk of software vulnerabilities (NIST SP 800-218 Rev. 1, Initial Public Draft). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-218r1.ipd",
    "url": "https://doi.org/10.6028/NIST.SP.800-218r1.ipd",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Five authors in that order, date, NIST SP 800-218 Rev. 1, title, and DOI `10.6028/NIST.SP.800-218r1.ipd` confirmed. **Initial Public Draft**, not a final standard; closed comment period does not make it final.",
    "evidence_urls": [
      "https://csrc.nist.gov/pubs/sp/800/218/r1/ipd"
    ]
  },
  {
    "id": 7,
    "apa": "Booth, H., Souppaya, M., Vassilev, A., Ogata, M., Stanley, M., & Scarfone, K. (2024). Secure software development practices for generative AI and dual-use foundation models: An SSDF community profile (NIST SP 800-218A). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-218A",
    "url": "https://doi.org/10.6028/NIST.SP.800-218A",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Six authors/order, title, NIST SP 800-218A, July 2024, and DOI `10.6028/NIST.SP.800-218A` confirmed from cover and front matter. The cover's title is preferable to the slightly inconsistent suggested-citation sentence inside the report.",
    "evidence_urls": [
      "https://doi.org/10.6028/NIST.SP.800-218A"
    ]
  },
  {
    "id": 8,
    "apa": "Cybersecurity and Infrastructure Security Agency, National Security Agency, Federal Bureau of Investigation, Australian Cyber Security Centre, Canadian Centre for Cyber Security, Computer Emergency Response Team New Zealand, New Zealand’s National Cyber Security Centre, United Kingdom’s National Cyber Security Centre, Germany’s Federal Office for Information Security, Netherlands’ National Cyber Security Centre, Norway’s National Cyber Security Center, Czech Republic’s National Cyber and Information Security Agency, Israel’s National Cyber Directorate, Korea Internet & Security Agency, Japan’s National Center of Incident Readiness and Strategy for Cybersecurity, Japan Computer Emergency Response Team Coordination Center, Cyber Security Agency of Singapore, & OAS/CICTE Network of Government Cyber Incident Response Teams (CSIRT) Americas. (2023, October). Shifting the balance of cybersecurity risk: Principles and approaches for secure by design software (Refined and expanded edition). https://www.cisa.gov/sites/default/files/2023-10/Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-Approaches-for-Secure-by-Design-Software.pdf",
    "url": "https://www.cisa.gov/sites/default/files/2023-10/Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-Approaches-for-Secure-by-Design-Software.pdf",
    "status": "corrected_from_primary_source",
    "note": "All 18 corporate authors expanded from the original report’s page 5 organizational-credit paragraph/list, preserving page-header credit order. Geographic possessives and Center/Centre spellings follow the report, not guessed current agency branding. Date and edition confirmed from October-update text. In-text: (Cybersecurity and Infrastructure Security Agency et al., 2023).",
    "evidence_urls": [
      "https://www.cisa.gov/sites/default/files/2023-10/Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-Approaches-for-Secure-by-Design-Software.pdf"
    ],
    "authors": [
      "Cybersecurity and Infrastructure Security Agency",
      "National Security Agency",
      "Federal Bureau of Investigation",
      "Australian Cyber Security Centre",
      "Canadian Centre for Cyber Security",
      "Computer Emergency Response Team New Zealand",
      "New Zealand’s National Cyber Security Centre",
      "United Kingdom’s National Cyber Security Centre",
      "Germany’s Federal Office for Information Security",
      "Netherlands’ National Cyber Security Centre",
      "Norway’s National Cyber Security Center",
      "Czech Republic’s National Cyber and Information Security Agency",
      "Israel’s National Cyber Directorate",
      "Korea Internet & Security Agency",
      "Japan’s National Center of Incident Readiness and Strategy for Cybersecurity",
      "Japan Computer Emergency Response Team Coordination Center",
      "Cyber Security Agency of Singapore",
      "OAS/CICTE Network of Government Cyber Incident Response Teams (CSIRT) Americas"
    ]
  },
  {
    "id": 9,
    "apa": "de Weck, O. (2015). Fundamentals of systems engineering [Course materials]. MIT OpenCourseWare. https://ocw.mit.edu/courses/16-842-fundamentals-of-systems-engineering-fall-2015/",
    "url": "https://ocw.mit.edu/courses/16-842-fundamentals-of-systems-engineering-fall-2015/",
    "status": "primary_metadata_matched",
    "note": "**Matched.** MIT OCW names Prof. Olivier de Weck as instructor and Fall 2015 as the course offering. Course 16.842 and title match.",
    "evidence_urls": [
      "https://ocw.mit.edu/courses/16-842-fundamentals-of-systems-engineering-fall-2015/"
    ]
  },
  {
    "id": 10,
    "apa": "Dijkstra, E. W. (1970). Notes on structured programming (EWD249; T.H. Report 70-WSK-03; 2nd ed.). Technological University Eindhoven. https://www.cs.utexas.edu/~EWD/transcriptions/EWD02xx/EWD249/EWD249.html",
    "url": "https://www.cs.utexas.edu/~EWD/transcriptions/EWD02xx/EWD249/EWD249.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Author archive transcript explicitly identifies EWD249, T.H. Report 70-WSK-03, second edition April 1970. The internal August 1969 date refers to the earlier text; it does not invalidate the 1970 edition citation.",
    "evidence_urls": [
      "https://www.cs.utexas.edu/~EWD/transcriptions/EWD02xx/EWD249/EWD249.html"
    ]
  },
  {
    "id": 11,
    "apa": "Grunbok, W., & Cole, M. (2018). Security in development: The IBM Secure Engineering Framework (IBM Redpaper REDP-4641-01). IBM Redbooks. https://www.redbooks.ibm.com/abstracts/redp4641.html",
    "url": "https://www.redbooks.ibm.com/abstracts/redp4641.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Warren Grunbok and Marie Cole, December 17, 2018, REDP-4641-01. ISBN 9780738457178 confirmed on publisher page.",
    "evidence_urls": [
      "https://www.redbooks.ibm.com/abstracts/redp4641.html"
    ]
  },
  {
    "id": 12,
    "apa": "Hirshorn, S. R., Voss, L. D., & Bromley, L. K. (2017). NASA systems engineering handbook (NASA/SP-2016-6105 Rev. 2). National Aeronautics and Space Administration. https://ntrs.nasa.gov/citations/20170001761",
    "url": "https://ntrs.nasa.gov/citations/20170001761",
    "status": "corrected_from_selected_primary_edition",
    "note": "Selected NTRS item 20170001761, the first NASA handbook source in governance/source-register.json. NTRS assigns publication date 2017-02-17 and authors Hirshorn, Voss, Bromley. Report identifier retains 2016. Current official attachment has 356 PDF pages and SHA256 3153ae2e53e29452d5997efafe280a5f05cd21b43a047e988a17e1dd5207a38e. Its first page is a contents page; no separate visible publication/copyright date supersedes the record date. PDF creation in 2016 is not publication evidence. The 297-page NASA landing-page file is a distinct presentation and is not silently substituted. Original historic download-byte identity unavailable. In-text: (Hirshorn et al., 2017).",
    "evidence_urls": [
      "https://ntrs.nasa.gov/api/citations/20170001761",
      "https://ntrs.nasa.gov/api/citations/20170001761/downloads/20170001761.pdf",
      "https://ntrs.nasa.gov/citations/20170001761"
    ],
    "in_text": "(Hirshorn et al., 2017)"
  },
  {
    "id": 13,
    "apa": "IBM. (n.d.). z/OS 3.2 system integrity. Retrieved August 31, 2026, from https://www.ibm.com/docs/en/zos/3.2.0?topic=aapmss-system-integrity",
    "url": "https://www.ibm.com/docs/en/zos/3.2.0?topic=aapmss-system-integrity",
    "status": "unresolved_source_access",
    "note": "**Partial.** Exact cited URL returns HTTP 403 through both retrieval routes. z/OS version, precise heading, and body cannot be called verified in this audit. No replacement version was substituted.",
    "evidence_urls": [
      "https://www.ibm.com/docs/en/zos/3.2.0?topic=aapmss-system-integrity"
    ]
  },
  {
    "id": 14,
    "apa": "IBM Policy. (n.d.-a). IBM artificial intelligence pillars. Retrieved August 31, 2026, from https://www.ibm.com/policy/blog/ibm-artificial-intelligence-pillars",
    "url": "https://www.ibm.com/policy/blog/ibm-artificial-intelligence-pillars",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Main heading matches; no page date exposed. Institutional author IBM / IBM Policy is consistent with the source site.",
    "evidence_urls": [
      "https://www.ibm.com/policy/blog/ibm-artificial-intelligence-pillars"
    ]
  },
  {
    "id": 15,
    "apa": "IBM Policy. (n.d.-b). IBM’s principles for trust and transparency. Retrieved August 31, 2026, from https://www.ibm.com/policy/blog/trust-principles",
    "url": "https://www.ibm.com/policy/blog/trust-principles",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Main heading matches the reference. Browser metadata inserts “Data,” but the displayed heading does not; retain the displayed heading. No date exposed.",
    "evidence_urls": [
      "https://www.ibm.com/policy/blog/trust-principles"
    ]
  },
  {
    "id": 16,
    "apa": "International Organization for Standardization, International Electrotechnical Commission, & Institute of Electrical and Electronics Engineers. (2023). Systems and software engineering—System life cycle processes (ISO/IEC/IEEE 15288:2023, 2nd ed.). https://www.iso.org/standard/81702.html",
    "url": "https://www.iso.org/standard/81702.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Title, organizations, edition 2, May 2023, and standard number confirmed.",
    "evidence_urls": [
      "https://www.iso.org/standard/81702.html"
    ]
  },
  {
    "id": 17,
    "apa": "International Organization for Standardization, International Electrotechnical Commission, & Institute of Electrical and Electronics Engineers. (2026). Systems and software engineering—Software life cycle processes (ISO/IEC/IEEE 12207:2026, 2nd ed.). https://www.iso.org/standard/90219.html",
    "url": "https://www.iso.org/standard/90219.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Published edition 2, April 2026, exact standard/title confirmed. It is not a draft in this catalog record.",
    "evidence_urls": [
      "https://www.iso.org/standard/90219.html"
    ]
  },
  {
    "id": 18,
    "apa": "Lockheed Martin. (2020, August 24). Lockheed Martin Software Factory continues to expand with accelerated software development capability. https://www.lockheedmartin.com/en-us/news/features/2020/lockheed-martin-software-factory-continues-expand-company-accelerates-software-development-capabilities.html",
    "url": "https://www.lockheedmartin.com/en-us/news/features/2020/lockheed-martin-software-factory-continues-expand-company-accelerates-software-development-capabilities.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Exact title and August 24, 2020 match publisher HTML title and embedded `publishDate`. Browser research fetch was denied; direct public-page retrieval succeeded.",
    "evidence_urls": [
      "https://www.lockheedmartin.com/en-us/news/features/2020/lockheed-martin-software-factory-continues-expand-company-accelerates-software-development-capabilities.html"
    ]
  },
  {
    "id": 19,
    "apa": "Lockheed Martin Skunk Works. (n.d.). The Skunk Works legacy. Retrieved August 31, 2026, from https://www.lockheedmartin.com/en-us/who-we-are/business-areas/aeronautics/skunkworks/skunk-works-origin-story.html",
    "url": "https://www.lockheedmartin.com/en-us/who-we-are/business-areas/aeronautics/skunkworks/skunk-works-origin-story.html",
    "status": "partial_metadata",
    "note": "**Partial / metadata refinement.** Publisher title is The Skunk Works® Legacy; current descriptive heading also adds “Developing the US's First Fighter Jet.” HTML `publishDate` is September 26, 2023, but this may describe page publication/migration, not the original historical essay. Preserve n.d. unless citing that current page revision explicitly; record the metadata date separately.",
    "evidence_urls": [
      "https://www.lockheedmartin.com/en-us/who-we-are/business-areas/aeronautics/skunkworks/skunk-works-origin-story.html"
    ]
  },
  {
    "id": 20,
    "apa": "Microsoft. (2022, June). Microsoft Responsible AI Standard v2: General requirements. https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Microsoft-Responsible-AI-Standard-General-Requirements.pdf",
    "url": "https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Microsoft-Responsible-AI-Standard-General-Requirements.pdf",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Cover confirms Microsoft, version 2, general requirements, June 2022, external release.",
    "evidence_urls": [
      "https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Microsoft-Responsible-AI-Standard-General-Requirements.pdf"
    ]
  },
  {
    "id": 21,
    "apa": "Microsoft. (2025, September 29). Microsoft Security Development Lifecycle (SDL). https://learn.microsoft.com/en-us/compliance/assurance/assurance-microsoft-security-development-lifecycle",
    "url": "https://learn.microsoft.com/en-us/compliance/assurance/assurance-microsoft-security-development-lifecycle",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Exact title and “Last updated on 2025-09-29” visible. This is an update date, not evidence that SDL originated in 2025.",
    "evidence_urls": [
      "https://learn.microsoft.com/en-us/compliance/assurance/assurance-microsoft-security-development-lifecycle"
    ]
  },
  {
    "id": 22,
    "apa": "Microsoft Industry Solutions Engineering. (n.d.). ISE Engineering Fundamentals Customer/Partner Engineering Playbook (Pinned commit 016770e43d8a75be87b98c000c049f07c4a6e6f8). Retrieved August 31, 2026, from https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/README.md",
    "url": "https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/README.md",
    "status": "corrected_from_primary_source",
    "note": "**Correction: formal title.** Pin `016770e43d8a75be87b98c000c049f07c4a6e6f8` exists. README title is ISE Engineering Fundamentals Customer/Partner Engineering Playbook; site title is Engineering Fundamentals Playbook, author Microsoft ISE. Commit date September 26, 2025 is a snapshot date, not proof every chapter was authored then. Preserve pin and n.d. unless explicitly dating the snapshot.",
    "evidence_urls": [
      "https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/README.md",
      "https://github.com/microsoft/code-with-engineering-playbook/blob/016770e43d8a75be87b98c000c049f07c4a6e6f8/mkdocs.yml"
    ]
  },
  {
    "id": 23,
    "apa": "MIT Office of Experiential Learning. (n.d.-a). About the Office of Experiential Learning: What is experiential learning? Retrieved August 31, 2026, from https://elo.mit.edu/about/",
    "url": "https://elo.mit.edu/about/",
    "status": "unresolved_source_access",
    "note": "**Partial.** Cited URL returned 502 in browser research and closed the direct connection. Exact heading/date/body unverified. Other MIT pages confirm the ELO domain, but do not independently verify this particular work.",
    "evidence_urls": [
      "https://elo.mit.edu/about/"
    ]
  },
  {
    "id": 24,
    "apa": "MIT Office of Experiential Learning. (n.d.-b). Best practices for experiential learning. Retrieved August 31, 2026, from https://elo.mit.edu/best-practices/",
    "url": "https://elo.mit.edu/best-practices/",
    "status": "unresolved_source_access",
    "note": "**Partial.** Same access failure as #23. Do not substitute unrelated MIT mentoring advice while retaining this title.",
    "evidence_urls": [
      "https://elo.mit.edu/best-practices/"
    ]
  },
  {
    "id": 25,
    "apa": "National Aeronautics and Space Administration, Office of the Chief Engineer. (2020, April 20). NASA software engineering handbook (NASA-HDBK-2203, Version D, Change 0). https://standards.nasa.gov/standard/NASA/NASA-HDBK-2203",
    "url": "https://standards.nasa.gov/standard/NASA/NASA-HDBK-2203",
    "status": "primary_metadata_matched",
    "note": "**Matched.** NASA catalog confirms document number, version d, change 0, April 20, 2020, responsible Office of Chief Engineer. It describes a wiki-based handbook; the catalog date does not freeze all current wiki content.",
    "evidence_urls": [
      "https://standards.nasa.gov/standard/NASA/NASA-HDBK-2203"
    ]
  },
  {
    "id": 26,
    "apa": "National Aeronautics and Space Administration, Office of the Chief Engineer. (2022, March 8). NASA software engineering requirements (NPR 7150.2D). https://nodis3.gsfc.nasa.gov/displayDir.cfm?c=7150&s=2D&t=NPR",
    "url": "https://nodis3.gsfc.nasa.gov/displayDir.cfm?c=7150&s=2D&t=NPR",
    "status": "primary_metadata_matched",
    "note": "**Matched.** NODIS confirms title, version, responsible office, effective March 8, 2022.",
    "evidence_urls": [
      "https://nodis3.gsfc.nasa.gov/displayDir.cfm?c=7150&s=2D&t=NPR"
    ]
  },
  {
    "id": 27,
    "apa": "National Aeronautics and Space Administration, Office of the Chief Engineer. (2023, July 5). NASA systems engineering processes and requirements (NPR 7123.1D, Change 2). https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_",
    "url": "https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_",
    "status": "partial_metadata",
    "note": "**Matched with date qualification.** NODIS confirms base effective date July 5, 2023 and current subject “Updated w/Change 2.” The audit did not retrieve the change log; do not describe July 5, 2023 as the separately verified date of Change 2.",
    "evidence_urls": [
      "https://nodis3.gsfc.nasa.gov/displayDir.cfm?Internal_ID=N_PR_7123_001D_"
    ]
  },
  {
    "id": 28,
    "apa": "NVIDIA. (n.d.). CUDA C++ best practices guide (Release 13.3). Retrieved August 31, 2026, from https://docs.nvidia.com/cuda/archive/13.3.0/cuda-c-best-practices-guide/index.html",
    "url": "https://docs.nvidia.com/cuda/archive/13.3.0/cuda-c-best-practices-guide/index.html",
    "status": "corrected_from_primary_source",
    "note": "**Correction: versioned link.** Current unversioned destination says 13.4; official archive confirms 13.3. Use archive URL when reusing this historical citation. No claim that DW/DEGS needs CUDA or tests NVIDIA hardware follows from this source. The archive URL was verified September 11, 2026. Historical August 31 retrieval refers to the original reference record, not a newly proven visit to this archive URL.",
    "evidence_urls": [
      "https://docs.nvidia.com/cuda/archive/13.3.0/cuda-c-best-practices-guide/index.html"
    ]
  },
  {
    "id": 29,
    "apa": "NVIDIA. (2025). NVIDIA sustainability report fiscal year 2025. https://images.nvidia.com/aem-dam/Solutions/documents/NVIDIA-Sustainability-Report-Fiscal-Year-2025.pdf",
    "url": "https://images.nvidia.com/aem-dam/Solutions/documents/NVIDIA-Sustainability-Report-Fiscal-Year-2025.pdf",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Cover/title, corporate author, copyright 2025, and approximately June 12, 2025 information date confirmed. Fiscal period ends January 26, 2025; fiscal year and publication year are distinct but both support this citation.",
    "evidence_urls": [
      "https://images.nvidia.com/aem-dam/Solutions/documents/NVIDIA-Sustainability-Report-Fiscal-Year-2025.pdf"
    ]
  },
  {
    "id": 30,
    "apa": "NVIDIA. (2026, April 15). Security development lifecycle for NVIDIA AI Enterprise [NVIDIA AI Enterprise Security White Paper]. https://docs.nvidia.com/ai-enterprise/planning-resource/ai-enterprise-security-white-paper/latest/security-lifecycle.html",
    "url": "https://docs.nvidia.com/ai-enterprise/planning-resource/ai-enterprise-security-white-paper/latest/security-lifecycle.html",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Title and last-updated April 15, 2026 confirmed. The URL is a mutable latest white-paper chapter; retain date and record an archive/snapshot if exact historical text matters.",
    "evidence_urls": [
      "https://docs.nvidia.com/ai-enterprise/planning-resource/ai-enterprise-security-white-paper/latest/security-lifecycle.html"
    ]
  },
  {
    "id": 31,
    "apa": "OWASP Foundation. (2025, May 30). OWASP application security verification standard (Version 5.0.0). https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release",
    "url": "https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release",
    "status": "primary_metadata_matched",
    "note": "**Matched; improve stability.** Official source release is tagged `v5.0.0_release`, published May 30, 2025. Avoid the automatically refreshed bleeding-edge release for a 5.0.0 citation.",
    "evidence_urls": [
      "https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release"
    ]
  },
  {
    "id": 32,
    "apa": "Parnas, D. L. (1972). On the criteria to be used in decomposing systems into modules. Communications of the ACM, 15(12), 1053–1058. https://doi.org/10.1145/361598.361623",
    "url": "https://doi.org/10.1145/361598.361623",
    "status": "publisher_deposited_registration_metadata",
    "note": "**Matched registration metadata; publisher access limited.** D. L. Parnas, December 1972, Communications of the ACM 15(12), 1053–1058, DOI `10.1145/361598.361623`. ACM page fetch denied; ACM-deposited DOI registration metadata confirmed the fields. Full paper not read for this audit.",
    "evidence_urls": [
      "https://doi.org/10.1145/361598.361623",
      "https://api.crossref.org/works/10.1145%2F361598.361623"
    ]
  },
  {
    "id": 33,
    "apa": "Saltzer, J. H., Reed, D. P., & Clark, D. D. (1984). End-to-end arguments in system design. ACM Transactions on Computer Systems, 2(4), 277–288. https://doi.org/10.1145/357401.357402",
    "url": "https://doi.org/10.1145/357401.357402",
    "status": "publisher_deposited_registration_metadata",
    "note": "**Matched registration metadata; publisher access limited.** Three authors/order, November 1984, ACM Transactions on Computer Systems 2(4), 277–288, DOI `10.1145/357401.357402` confirmed from ACM-deposited DOI metadata. Full paper not read for this audit.",
    "evidence_urls": [
      "https://doi.org/10.1145/357401.357402",
      "https://api.crossref.org/works/10.1145/357401.357402"
    ]
  },
  {
    "id": 34,
    "apa": "SEBoK Editorial and Governing Boards. (2026). Guide to the systems engineering body of knowledge (SEBoK) (Version 2.14). https://sebokwiki.org/w/index.php?title=Version_2.14&oldid=78836",
    "url": "https://sebokwiki.org/w/index.php?title=Version_2.14&oldid=78836",
    "status": "partial_metadata",
    "note": "**Matched version; attribution qualified.** Release page confirms May 18, 2026 and names both boards, editor-in-chief Nicole Hutchison, and managing editor Chris Hoffman. Treat the printed collective-author form as a descriptive credit, not a verified publisher-prescribed citation. Version page is release information, not a frozen copy of every linked article.",
    "evidence_urls": [
      "https://sebokwiki.org/wiki/Version_2.14",
      "https://sebokwiki.org/w/index.php?title=Version_2.14&oldid=78836"
    ]
  },
  {
    "id": 35,
    "apa": "SLSA Community. (2025, November 24). SLSA specification (Version 1.2). https://slsa.dev/spec/v1.2/",
    "url": "https://slsa.dev/spec/v1.2/",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official specification is approved v1.2. Official announcement source dated November 24, 2025 names SLSA Community.",
    "evidence_urls": [
      "https://slsa.dev/spec/v1.2/",
      "https://github.com/slsa-framework/slsa/blob/main/www/_posts/2025-11-24-announce-slsa-v1.2.md"
    ]
  },
  {
    "id": 36,
    "apa": "Souppaya, M., Scarfone, K., & Dodson, D. (2022). Secure software development framework (SSDF) version 1.1: Recommendations for mitigating the risk of software vulnerabilities (NIST SP 800-218). National Institute of Standards and Technology. https://doi.org/10.6028/NIST.SP.800-218",
    "url": "https://doi.org/10.6028/NIST.SP.800-218",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Three authors/order, NIST SP 800-218, title, February 2022 publication, DOI `10.6028/NIST.SP.800-218` confirmed. Distinguish this final version from #6's draft revision.",
    "evidence_urls": [
      "https://csrc.nist.gov/pubs/sp/800/218/final"
    ]
  },
  {
    "id": 37,
    "apa": "Swift project. (n.d.). Swift evolution process (Pinned commit c8623621aacc8e3f364bb0f3cb07675177a1ec4e). Retrieved August 31, 2026, from https://github.com/swiftlang/swift-evolution/blob/c8623621aacc8e3f364bb0f3cb07675177a1ec4e/process.md",
    "url": "https://github.com/swiftlang/swift-evolution/blob/c8623621aacc8e3f364bb0f3cb07675177a1ec4e/process.md",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Commit `c8623621aacc8e3f364bb0f3cb07675177a1ec4e` exists (August 27, 2026); pinned `process.md` title matches. Swift project collective credit is appropriate; the merge committer is not the sole author of the document.",
    "evidence_urls": [
      "https://github.com/swiftlang/swift-evolution/blob/c8623621aacc8e3f364bb0f3cb07675177a1ec4e/process.md"
    ]
  },
  {
    "id": 38,
    "apa": "U.S. Department of Defense. (2020a, November 18). Engineering of Defense Systems (DoD Instruction 5000.88). https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500088p.pdf",
    "url": "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500088p.pdf",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official PDF cover confirms number, title, effective November 18, 2020, originating OUSD(R&E). Lowercase `.pdf` route accessible where uppercase retrieval failed.",
    "evidence_urls": [
      "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500088p.pdf"
    ]
  },
  {
    "id": 39,
    "apa": "U.S. Department of Defense. (2020b, October 2). Operation of the Software Acquisition Pathway (DoD Instruction 5000.87). https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500087p.pdf",
    "url": "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500087p.pdf",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official PDF confirms number/title/date and originating OUSD(A&S). The 2020a/2020b title order in the original bibliography is consistent: Engineering precedes Operation.",
    "evidence_urls": [
      "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500087p.pdf"
    ]
  },
  {
    "id": 40,
    "apa": "U.S. Department of Defense. (2023a, December 21). Digital engineering (DoD Instruction 5000.97). https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500097p.PDF",
    "url": "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500097p.PDF",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official cover confirms exact title, date, number, and OUSD(R&E). Author correction creates same-author 2023 pair; use 2023a for Digital engineering and 2023b for System safety consistently in text.",
    "evidence_urls": [
      "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodi/500097p.PDF"
    ]
  },
  {
    "id": 41,
    "apa": "U.S. Department of Defense. (2024, December 9). Operational test and evaluation and live fire test and evaluation of artificial intelligence-enabled and autonomous systems (DoD Manual 5000.101). https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodm/5000101p.PDF?ver=FfOR56lIK5S1LDFfSlYwYQ%3D%3D",
    "url": "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodm/5000101p.PDF?ver=FfOR56lIK5S1LDFfSlYwYQ%3D%3D",
    "status": "primary_metadata_matched",
    "note": "**Matched.** Official PDF title/date/number confirmed; 25-page PDF accessible using official version-query URL. This does not show that DW/DEGS underwent military operational testing.",
    "evidence_urls": [
      "https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodm/5000101p.PDF?ver=FfOR56lIK5S1LDFfSlYwYQ%3D%3D"
    ]
  },
  {
    "id": 42,
    "apa": "U.S. Department of Defense. (2022, June). Responsible artificial intelligence strategy and implementation pathway. https://media.defense.gov/2022/Jun/22/2003022604/-1/-1/0/Department-of-Defense-Responsible-Artificial-Intelligence-Strategy-and-Implementation-Pathway.PDF",
    "url": "https://media.defense.gov/2022/Jun/22/2003022604/-1/-1/0/Department-of-Defense-Responsible-Artificial-Intelligence-Strategy-and-Implementation-Pathway.PDF",
    "status": "corrected_from_primary_source",
    "note": "**Correction: preparer credit / accessible URL.** Cover confirms June 2022 and title; it explicitly says prepared by DoD Responsible AI Working Council. Use U.S. Department of Defense, Responsible AI Working Council as credited preparer, or DoD as corporate author plus a clear preparer note. CDAO is a related implementation office, not the named preparer on this cover. Supplemental credit to print: Prepared by the DoD Responsible AI Working Council.",
    "evidence_urls": [
      "https://media.defense.gov/2022/Jun/22/2003022604/-1/-1/0/Department-of-Defense-Responsible-Artificial-Intelligence-Strategy-and-Implementation-Pathway.PDF"
    ]
  },
  {
    "id": 43,
    "apa": "U.S. Department of Defense. (2023b, September 27). System safety (MIL-STD-882E, Change 1). https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027",
    "url": "https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027",
    "status": "corrected_from_primary_source",
    "note": "**Correction: distinguish host from author.** Official DLA-hosted cover confirms Department of Defense standard practice, number/change/title/date. Concluding material names preparing activity Air Force–40. Recommend U.S. Department of Defense as corporate author, DLA ASSIST as catalog host. Exact catalog fetch failed; official indexed PDF and concluding material confirm metadata. Author correction creates same-author 2023 pair; use 2023a for Digital engineering and 2023b for System safety consistently in text.",
    "evidence_urls": [
      "https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=36027",
      "https://quicksearch.dla.mil/Transient/411C31BE0E0C4F898EACDFE832107967.pdf"
    ]
  },
  {
    "id": 44,
    "apa": "Walden, D. D., Shortell, T. M., Roedler, G. J., Delicado, B. A., Mornas, O., Yip, Y.-S., & Endler, D. (Eds.). (2023). INCOSE systems engineering handbook: A guide for system life cycle processes and activities (5th ed.). John Wiley & Sons. https://catalogimages.wiley.com/images/db/pdf/9781119814290.excerpt.pdf",
    "url": "https://catalogimages.wiley.com/images/db/pdf/9781119814290.excerpt.pdf",
    "status": "partial_metadata",
    "note": "**Matched core metadata; report identifier unresolved.** Wiley excerpt explicitly names all seven editors in printed order, subtitle, fifth edition, 2023, John Wiley & Sons Ltd. INCOSE verifies ISBN 978-1-119-81429-0. The additional identifier `INCOSE-TP-2003-002-05-2023` was not confirmed in accessible front matter; omit it from a corrected citation pending exact evidence. Preserve editor spelling Shortell; one INCOSE catalog page inconsistently says Shortall.",
    "evidence_urls": [
      "https://catalogimages.wiley.com/images/db/pdf/9781119814290.excerpt.pdf",
      "https://www.incose.org/resources-publications/technical-publications/se-handbook/"
    ]
  }
]
```

## Bounded follow-up: joint authors and selected NASA edition

Record #8 now expands every one of the 18 header acronyms from the **same original CISA report, page 5**, retaining header order. Country possessives and the Norwegian “Center” spelling follow the source text. These are the organizations credited in the October 2023 document; they are not silently replaced with later agency names. In-text citation: **(Cybersecurity and Infrastructure Security Agency et al., 2023)**. [Original joint report, page 5](https://www.cisa.gov/sites/default/files/2023-10/Shifting-the-Balance-of-Cybersecurity-Risk-Principles-and-Approaches-for-Secure-by-Design-Software.pdf).

For #12, the local [source register](governance/source-register.json:37) already distinguishes the report's 2016 identifier from NTRS publication on February 17, 2017. Its first official location is the old NTRS path for item 20170001761; its second location is the NASA handbook landing page. The old archive URL now returns an HTML page, so the current NTRS metadata/download endpoints were used for the same record. That is the selected source for the revised reference, not a claim that its current bytes match an unavailable historical download.

**Recommended reference:** Hirshorn, S. R., Voss, L. D., & Bromley, L. K. (2017). *NASA systems engineering handbook* (NASA/SP-2016-6105 Rev. 2). National Aeronautics and Space Administration. https://ntrs.nasa.gov/citations/20170001761

**Recommended in-text citation:** **(Hirshorn et al., 2017)**, or **Hirshorn et al. (2017)** in narrative text. Use that author/year consistently in both the full bibliography and the figure subset. NASA remains the publisher; do not silently switch the figure's author to NASA while retaining this three-author reference.

The [selected official attachment](https://ntrs.nasa.gov/api/citations/20170001761/downloads/20170001761.pdf) has 356 PDF pages and SHA-256 `3153ae2e53e29452d5997efafe280a5f05cd21b43a047e988a17e1dd5207a38e`. The first page is a contents page headed NASA Systems Engineering Handbook Rev 2. Its preface identifies NASA/SP-2016-6105 Rev 2. No separate visible publication/copyright date was found in the inspected opening matter that overrides NTRS's publication date. PDF metadata records September 20, 2016 creation and February 23, 2017 modification; those technical timestamps are not substituted for publication. The author field there is a production username, so bibliographic authors come from the authoritative NTRS record.

The different [NASA landing-page designed PDF](https://www.nasa.gov/wp-content/uploads/2018/09/nasa_systems_engineering_handbook_0.pdf) has 297 PDF pages and SHA-256 `8eeb4887a4dc57a23049da7dd2ed556833cf98e214b240468d987873164ff688`. Cover, inside cover, preface, and acknowledgments were inspected: institutional NASA cover; Hirshorn listed as contact; all three names among many contributors; report identifier includes 2016. Its creation/modification metadata is June 2017. This file does not prove a 2016 publication date for the separately selected NTRS attachment and is not the file selected in revised record #12. Figure quotations/page locators must therefore use the selected attachment or explicitly identify the alternative file.
