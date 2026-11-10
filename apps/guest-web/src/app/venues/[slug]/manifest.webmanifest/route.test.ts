import { describe, expect, it } from "vitest";
import { GET } from "./route";

const call = (slug: string) => GET(new Request("http://x"), { params: Promise.resolve({ slug }) });

describe("venue manifest", () => {
  it("names and colours the installed app as the venue", async () => {
    const res = await call("angeethi-house");
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("manifest+json");
    const m = await res.json();
    expect(m.name).toBe("Angeethi House");
    expect(m.theme_color).toBe("#7f011f");
    expect(m.icons[0].src).toBe("/venues/angeethi-house/mark.svg");
    expect(JSON.stringify(m)).not.toContain("Mise");
  });
  it("is 404 for an unknown or hostile slug", async () => {
    for (const slug of ["nope", "__proto__", "..%2F", ""]) expect((await call(slug)).status).toBe(404);
  });
});
