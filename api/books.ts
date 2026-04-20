/**
 * /api/books — Amazon Product Advertising API v5 proxy.
 *
 * Required environment variables (set in Vercel Project Settings):
 *   AMAZON_PA_ACCESS_KEY  — PA-API access key ID
 *   AMAZON_PA_SECRET_KEY  — PA-API secret access key
 *   AMAZON_PA_PARTNER_TAG — your Amazon Associates partner tag (e.g. "hosaka-20")
 *   AMAZON_PA_REGION      — PA-API region (default: "us-east-1")
 *
 * If any required variable is missing the handler returns 501 so the
 * BooksPanel can detect the unconfigured state and show a friendly message.
 *
 * Query parameter:
 *   q — search keyword string (required)
 *
 * Response shape:
 *   { results: BookResult[] }
 *
 * BookResult:
 *   { asin, title, authors[], imageUrl?, price?, url, kindleUrl?, binding? }
 */

import type { VercelRequest, VercelResponse } from "@vercel/node";
import { createHmac, createHash } from "crypto";

const PA_HOST_MAP: Record<string, string> = {
  "us-east-1": "webservices.amazon.com",
  "eu-west-1": "webservices.amazon.co.uk",
  "us-west-2": "webservices.amazon.com",
  "ap-northeast-1": "webservices.amazon.co.jp",
  "ap-southeast-1": "webservices.amazon.com.au",
};

function computeHmacSha256(key: string | Buffer, data: string): Buffer {
  return createHmac("sha256", key).update(data, "utf8").digest();
}

function sha256Hex(data: string): string {
  return createHash("sha256").update(data, "utf8").digest("hex");
}

function getSigningKey(secretKey: string, dateStamp: string, region: string): Buffer {
  const kDate = computeHmacSha256("AWS4" + secretKey, dateStamp);
  const kRegion = computeHmacSha256(kDate, region);
  const kService = computeHmacSha256(kRegion, "ProductAdvertisingAPI");
  return computeHmacSha256(kService, "aws4_request");
}

function toAmzDate(now: Date): { amzDate: string; dateStamp: string } {
  const iso = now.toISOString().replace(/[:-]/g, "").replace(/\.\d+/, "");
  return { amzDate: iso, dateStamp: iso.slice(0, 8) };
}

interface PaApiItem {
  ASIN?: string;
  ItemInfo?: {
    Title?: { DisplayValue?: string };
    ByLineInfo?: { Contributors?: Array<{ Name?: string; RoleType?: string }> };
    Classifications?: { Binding?: { DisplayValue?: string } };
  };
  Images?: {
    Primary?: { Medium?: { URL?: string } };
  };
  Offers?: {
    Listings?: Array<{
      Price?: { DisplayAmount?: string };
    }>;
  };
  DetailPageURL?: string;
}

interface PaApiResponse {
  SearchResult?: {
    Items?: PaApiItem[];
  };
  Errors?: Array<{ Code?: string; Message?: string }>;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Only GET allowed
  if (req.method !== "GET") {
    return res.status(405).json({ error: "method not allowed" });
  }

  const accessKey = process.env.AMAZON_PA_ACCESS_KEY;
  const secretKey = process.env.AMAZON_PA_SECRET_KEY;
  const partnerTag = process.env.AMAZON_PA_PARTNER_TAG;
  const region = process.env.AMAZON_PA_REGION ?? "us-east-1";

  if (!accessKey || !secretKey || !partnerTag) {
    return res.status(501).json({
      error:
        "books relay not configured. set AMAZON_PA_ACCESS_KEY, AMAZON_PA_SECRET_KEY, AMAZON_PA_PARTNER_TAG.",
    });
  }

  const q = typeof req.query.q === "string" ? req.query.q.trim() : "";
  if (!q) {
    return res.status(400).json({ error: "q parameter required" });
  }

  const host = PA_HOST_MAP[region] ?? PA_HOST_MAP["us-east-1"];
  const path = "/paapi5/searchitems";
  const service = "ProductAdvertisingAPI";

  const payload = JSON.stringify({
    Keywords: q,
    Resources: [
      "Images.Primary.Medium",
      "ItemInfo.Title",
      "ItemInfo.ByLineInfo",
      "ItemInfo.Classifications",
      "Offers.Listings.Price",
    ],
    SearchIndex: "Books",
    ItemCount: 10,
    PartnerTag: partnerTag,
    PartnerType: "Associates",
    Marketplace: "www.amazon.com",
  });

  const now = new Date();
  const { amzDate, dateStamp } = toAmzDate(now);

  const canonicalHeaders =
    `content-encoding:amz-1.0\n` +
    `content-type:application/json; charset=utf-8\n` +
    `host:${host}\n` +
    `x-amz-date:${amzDate}\n` +
    `x-amz-target:com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems\n`;

  const signedHeaders =
    "content-encoding;content-type;host;x-amz-date;x-amz-target";

  const payloadHash = sha256Hex(payload);

  const canonicalRequest =
    `POST\n${path}\n\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`;

  const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
  const stringToSign =
    `AWS4-HMAC-SHA256\n${amzDate}\n${credentialScope}\n${sha256Hex(canonicalRequest)}`;

  const signingKey = getSigningKey(secretKey, dateStamp, region);
  const signature = createHmac("sha256", signingKey)
    .update(stringToSign, "utf8")
    .digest("hex");

  const authHeader =
    `AWS4-HMAC-SHA256 Credential=${accessKey}/${credentialScope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;

  try {
    const apiRes = await fetch(`https://${host}${path}`, {
      method: "POST",
      headers: {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        host,
        "x-amz-date": amzDate,
        "x-amz-target":
          "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems",
        authorization: authHeader,
      },
      body: payload,
    });

    const data = (await apiRes.json().catch(() => ({}))) as PaApiResponse;

    if (!apiRes.ok) {
      const msg =
        data.Errors?.[0]?.Message ??
        `amazon paapi returned http ${apiRes.status}`;
      return res.status(502).json({ error: msg });
    }

    const items = data.SearchResult?.Items ?? [];
    const results = items.map((item: PaApiItem) => {
      const asin = item.ASIN ?? "";
      const title = item.ItemInfo?.Title?.DisplayValue ?? "(untitled)";
      const contributors = item.ItemInfo?.ByLineInfo?.Contributors ?? [];
      const authors = contributors
        .filter((c) => c.RoleType === "author")
        .map((c) => c.Name ?? "")
        .filter(Boolean);
      const imageUrl = item.Images?.Primary?.Medium?.URL;
      const price = item.Offers?.Listings?.[0]?.Price?.DisplayAmount;
      const binding =
        item.ItemInfo?.Classifications?.Binding?.DisplayValue;
      const url = item.DetailPageURL ?? `https://www.amazon.com/dp/${asin}`;
      const kindleUrl = asin
        ? `https://www.amazon.com/dp/${asin}/ref=tmm_kin_swatch_0`
        : undefined;
      return { asin, title, authors, imageUrl, price, url, kindleUrl, binding };
    });

    res.setHeader(
      "cache-control",
      "public, s-maxage=300, stale-while-revalidate=60",
    );
    return res.status(200).json({ results });
  } catch (err) {
    return res
      .status(502)
      .json({ error: `relay error: ${(err as Error).message}` });
  }
}
