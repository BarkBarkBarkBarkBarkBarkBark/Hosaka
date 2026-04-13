"use server"

export interface FormState {
  success: boolean
  message: string
}

const initialState: FormState = { success: false, message: "" }
export { initialState }

export async function submitLeadForm(
  _prevState: FormState,
  formData: FormData
): Promise<FormState> {
  const email = (formData.get("email") as string)?.trim()

  if (!email || !email.includes("@") || !email.includes(".")) {
    return { success: false, message: "Please enter a valid email address." }
  }

  // TODO: Integrate email service (Resend, Formspree, ConvertKit, etc.)
  console.log("[Lead Capture]", { email, timestamp: new Date().toISOString() })

  return {
    success: true,
    message: "You're on the list. We'll be in touch when preorders open.",
  }
}

export async function submitContactForm(
  _prevState: FormState,
  formData: FormData
): Promise<FormState> {
  const name = (formData.get("name") as string)?.trim()
  const email = (formData.get("email") as string)?.trim()
  const type = (formData.get("type") as string)?.trim()
  const message = (formData.get("message") as string)?.trim()

  if (!name || !email || !message) {
    return { success: false, message: "Please fill in all required fields." }
  }

  if (!email.includes("@") || !email.includes(".")) {
    return { success: false, message: "Please enter a valid email address." }
  }

  if (message.length < 10) {
    return {
      success: false,
      message: "Please provide a bit more detail in your message.",
    }
  }

  // TODO: Integrate email service
  console.log("[Contact Form]", {
    name,
    email,
    type,
    message,
    timestamp: new Date().toISOString(),
  })

  return {
    success: true,
    message:
      "Message received. We'll get back to you within 1–2 business days.",
  }
}

export async function submitPreorderForm(
  _prevState: FormState,
  formData: FormData
): Promise<FormState> {
  const name = (formData.get("name") as string)?.trim()
  const email = (formData.get("email") as string)?.trim()
  const company = (formData.get("company") as string)?.trim()
  const product = (formData.get("product") as string)?.trim()
  const useCase = (formData.get("useCase") as string)?.trim()
  const budget = (formData.get("budget") as string)?.trim()

  if (!name || !email || !product) {
    return {
      success: false,
      message: "Please fill in your name, email, and product interest.",
    }
  }

  if (!email.includes("@") || !email.includes(".")) {
    return { success: false, message: "Please enter a valid email address." }
  }

  // TODO: Integrate CRM / email service
  console.log("[Preorder Form]", {
    name,
    email,
    company,
    product,
    useCase,
    budget,
    timestamp: new Date().toISOString(),
  })

  return {
    success: true,
    message:
      "You're on the preorder list. We'll reach out with next steps as your selected configuration approaches availability.",
  }
}
