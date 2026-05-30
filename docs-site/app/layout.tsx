import type { Metadata } from "next";
import { Footer, Layout, Navbar } from "nextra-theme-docs";
import { Banner, Head } from "nextra/components";
import { getPageMap } from "nextra/page-map";
import "nextra-theme-docs/style.css";

export const metadata: Metadata = {
  title: {
    default: "chemcellar docs",
    template: "%s – chemcellar docs",
  },
  description:
    "User documentation for chemcellar — a chemical compound management & screening platform.",
};

const wordmark = (
  <span style={{ fontWeight: 700, letterSpacing: "-0.02em" }}>chemcellar</span>
);

const navbar = (
  <Navbar
    logo={wordmark}
    projectLink="https://github.com/sidxz/cellar"
  />
);

const footer = (
  <Footer>
    <span>
      {new Date().getFullYear()} © chemcellar ·{" "}
      <a
        href="https://github.com/sidxz/cellar"
        target="_blank"
        rel="noreferrer"
        style={{ textDecoration: "underline" }}
      >
        github.com/sidxz/cellar
      </a>
    </span>
  </Footer>
);

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          banner={
            <Banner storageKey="chemcellar-docs">
              chemcellar documentation — work in progress
            </Banner>
          }
          navbar={navbar}
          footer={footer}
          pageMap={await getPageMap()}
          docsRepositoryBase="https://github.com/sidxz/cellar/tree/main/docs-site"
          editLink="Edit this page on GitHub"
          sidebar={{ defaultMenuCollapseLevel: 1, toggleButton: true }}
        >
          {children}
        </Layout>
      </body>
    </html>
  );
}
