# Official CUMCM Rules Reference

Source files reviewed:

- `D:/Data/Download/math/reference/论文规范/全国大学生数学建模竞赛论文格式规范（2026年修订稿）(2).pdf`
- `D:/Data/Download/math/reference/论文规范/全国大学生数学建模竞赛人工智能工具使用规定 （2026年试行）(1).pdf`

These are P0 rules for this skill. If older templates or excellent papers differ, use these rules.

## Mandatory Paper Format Rules

【强制】Paper copy:

- Use white A4 paper; single-sided or double-sided printing is allowed.
- Margins: at least 2.5 cm on top, bottom, left, and right.
- Bind from the left side.
- Page 1 is the commitment letter.
- Page 2 is the numbering page.
- Page 3 is the abstract page.
- The abstract page contains title, abstract, and keywords; no English translation is required.
- The abstract page should not exceed one page in principle.
- Page numbering starts on the abstract page, centered in the footer, using Arabic numerals starting from 1.
- The main text starts on page 4.
- Do not include a table of contents.
- The main text must not exceed 30 pages.
- Appendices follow the main text; appendix page count is unlimited for the paper copy.
- Appendices must be printed and bound together with the main text.

【强制】Appendix and code:

- Appendices should include the support-material file list.
- Appendices should include all complete runnable source programs used for modeling, including interactive commands for Excel, SPSS, and similar tools when applicable.
- If necessary source code is missing, code cannot run, or code results differ from the paper, award eligibility may be cancelled.
- If no program was used, the appendix must explicitly state that no program was used.

【强制】Anonymity:

- The abstract page, main text, and appendices must not contain participant identity, school, or competition-region information.
- Support-material files must also avoid participant identity, school, or competition-region information.
- Check visible text, code comments, metadata-like paths, screenshots, document properties when possible, and absolute local paths in code listings.

【强制】References:

- All cited external or public materials, including online materials, must be listed according to scientific-paper norms.
- Citations must be marked at the relevant place in the main text.

【强制】Electronic submission:

- Submit the paper and support materials according to the current participation instructions.
- The electronic paper content and format, including appendices, must match the paper copy.
- The electronic paper must be one separate file, PDF or Word; PDF is recommended.
- The electronic paper file must not exceed 20 MB.
- Do not compress the electronic paper file.
- Do not include the commitment letter or numbering page in the electronic paper; the electronic paper's first page must be the abstract page.
- Support materials must be compressed into one RAR or ZIP file and must not exceed 20 MB.
- Support materials include all necessary materials supporting models, results, and conclusions. At minimum, include runnable source programs and independently collected data used in the work; large intermediate-result figures/tables may also belong there.
- The support-material file list should be placed in the paper appendix.
- If there is no support-material file, the appendix should state that the paper has no support materials.
- If support materials do not match the paper, the paper may lose award eligibility.
- Do not include commitment letter or numbering page in support materials.

【官方未统一规定】

- Font, font size, line spacing, and colors are not nationally unified in the 2026 format document unless local contest-area rules add requirements.
- When the project template imposes a style, follow the template unless it conflicts with P0 rules.

## Mandatory AI-Use Rules

【强制】Scope and responsibility:

- The AI-use rule applies to large language models, generative AI, code assistants, AI agents, and similar tools.
- AI use is allowed but not required.
- Core modeling and analysis must be participant-led.
- AI-assisted content must be manually reviewed and verified item by item.

【强制】Paper statement placement:

- Place an `AI 工具使用声明` before `参考文献`.
- Use one of the official statement patterns depending on whether AI was used.

【强制】If no AI tool was used:

- State that the team did not use any AI tool during the competition.

【强制】If AI tools were used:

- State that AI tools were used and briefly name purposes such as language polishing or code debugging.
- State that detailed usage is in support materials.
- Support materials must include a PDF named `AI 工具使用详情.pdf`.
- That PDF must include: AI tool names and versions/models; purposes and workflow stages; main prompting mode and process description, with typical examples if useful; and how outputs were adopted, manually modified, and verified, except ordinary language polishing details may be simplified.

【禁止】

- Do not hide AI use.
- Do not make false AI-use statements.
- Do not submit unreviewed or unverified AI-generated content as core modeling and analysis.

## Execution and Review Checks

When writing or reviewing a paper:

- Check paper order separately for paper copy and electronic paper because commitment/numbering pages differ.
- Count body pages from the main text only; appendices are not part of the 30-page body limit.
- Verify that appendix and support-material lists match actual files.
- Verify that all code-backed results in the paper can be produced by included source code or documented computation.
- Search for school names, participant names, region names, absolute user paths, email addresses, phone numbers, account names, and screenshots that may reveal identity.
- If AI tools are used in the project workflow, prepare the AI statement and support-material PDF instead of omitting it.
