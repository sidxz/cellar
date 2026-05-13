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
      mode: "tags-split",
      override: {
        mutator: {
          path: "src/shared/lib/api/custom-instance.ts",
          name: "customInstance",
        },
        query: {
          useQuery: true,
        },
      },
    },
  },
});
