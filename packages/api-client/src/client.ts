import createClient, { type Client } from "openapi-fetch";
import type { components, paths } from "./generated/schema";

export type { components, paths };
export type Schemas = components["schemas"];

export type ApiPaths = paths;
export type ApiClient = Client<paths>;

export function createApiClient(baseUrl = ""): ApiClient {
  return createClient<paths>({ baseUrl });
}

export const client: ApiClient = createClient<paths>({ baseUrl: "" });
export default client;
