import Link from "next/link";
import type { ComponentProps } from "react";

type LinkProps = ComponentProps<typeof Link>;
type DenseLinkProps = Omit<LinkProps, "href"> & {
  href: LinkProps["href"] | string;
};

export function DenseLink({ href, prefetch = false, ...props }: DenseLinkProps) {
  return <Link {...props} href={href as LinkProps["href"]} prefetch={prefetch} />;
}
