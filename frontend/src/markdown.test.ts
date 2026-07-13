import { describe, expect, it } from "vitest";
import { escapeHtml, renderMarkdown } from "./markdown";

describe("escapeHtml", () => {
  it("escapes the five HTML-significant characters", () => {
    expect(escapeHtml(`<script>&"'</script>`)).toBe(
      "&lt;script&gt;&amp;&quot;&#39;&lt;/script&gt;",
    );
  });

  it("leaves plain text untouched", () => {
    expect(escapeHtml("just a normal sentence")).toBe("just a normal sentence");
  });
});

describe("renderMarkdown", () => {
  it("wraps a single paragraph in <p>", () => {
    expect(renderMarkdown("hello there")).toBe("<p>hello there</p>");
  });

  it("splits on a blank line into separate paragraphs", () => {
    expect(renderMarkdown("first\n\nsecond")).toBe("<p>first</p><p>second</p>");
  });

  it("converts a single newline within a paragraph to <br>", () => {
    expect(renderMarkdown("line one\nline two")).toBe("<p>line one<br>line two</p>");
  });

  it("converts **bold** to <strong>", () => {
    expect(renderMarkdown("this is **important**")).toBe("<p>this is <strong>important</strong></p>");
  });

  it("converts [label](url) to a safe, new-tab link for http/https", () => {
    expect(renderMarkdown("see [my site](https://example.com)")).toBe(
      '<p>see <a href="https://example.com" target="_blank" rel="noopener noreferrer">my site</a></p>',
    );
  });

  it("converts a mailto: link", () => {
    expect(renderMarkdown("[email me](mailto:test@example.com)")).toBe(
      '<p><a href="mailto:test@example.com" target="_blank" rel="noopener noreferrer">email me</a></p>',
    );
  });

  it("does not linkify unsafe schemes (e.g. javascript:)", () => {
    const out = renderMarkdown("[click](javascript:alert(1))");
    expect(out).not.toContain("<a ");
    expect(out).toContain("[click](javascript:alert(1))");
  });

  it("escapes HTML in the input before applying markdown, preventing injection", () => {
    const out = renderMarkdown("<img src=x onerror=alert(1)> and **bold**");
    expect(out).toBe("<p>&lt;img src=x onerror=alert(1)&gt; and <strong>bold</strong></p>");
  });

  it("escapes HTML that looks like a link/bold marker without becoming real markup", () => {
    // The label/url text itself still gets escaped even inside a real link.
    expect(renderMarkdown("[<b>x</b>](https://example.com)")).toBe(
      '<p><a href="https://example.com" target="_blank" rel="noopener noreferrer">&lt;b&gt;x&lt;/b&gt;</a></p>',
    );
  });
});
