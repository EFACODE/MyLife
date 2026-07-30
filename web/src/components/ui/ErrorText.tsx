export function ErrorText({ children }: { children: string }) {
  return (
    <p role="alert" className="text-sm text-red-600">
      {children}
    </p>
  );
}
