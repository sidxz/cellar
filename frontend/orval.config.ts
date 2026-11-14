import { defineConfig } from "orval";

export default defineConfig({
  cellar: {
    input: {
      target: "http://localhost:8000/openapi.json",
    },
    output: {
      target: "src/shared/lib/api/endpoints.ts",
      schemas: "src/shared/lib/api/model",
      client: "react-query",
      // customInstance uses fetch but resolves to the parsed body, which is
      // the axios-style contract. orval's "fetch" mode would type every
      // response as { data, status, headers }. No axios import is generated.
      httpClient: "axios",
      mode: "tags-split",
      override: {
        mutator: {
          path: "src/shared/lib/api/custom-instance.ts",
          name: "customInstance",
        },
      },
    },
  },
});
