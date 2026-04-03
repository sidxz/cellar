import { defineConfig } from "orval";

export default defineConfig({
  chemVault: {
    input: {
      target: "http://localhost:8000/openapi.json",
    },
    output: {
      target: "src/lib/api/endpoints.ts",
      schemas: "src/lib/api/model",
      client: "react-query",
      mode: "tags-split",
      override: {
        mutator: {
          path: "src/lib/api/custom-instance.ts",
          name: "customInstance",
        },
        query: {
          useQuery: true,
        },
      },
    },
  },
});
