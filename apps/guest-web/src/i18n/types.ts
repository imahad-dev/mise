export interface TranslationDict {
  staffNotice: string;
  allergens: {
    gluten: string;
    milk: string;
    eggs: string;
    fish: string;
    crustaceans: string;
    molluscs: string;
    tree_nuts: string;
    peanuts: string;
    soy: string;
    celery: string;
    mustard: string;
    sesame: string;
    sulphites: string;
    lupin: string;
  };
  dietary: {
    vegetarian: string;
    vegan: string;
    gluten_free: string;
  };
  allergenStatus: {
    contains: string;
    unverified: string;
    no_declared_match: string;
  };
  ui: {
    welcomeTitle: string;
    welcomeSubtitle: string;
    selectLanguage: string;
    selectDietary: string;
    selectAllergens: string;
    continueToMenu: string;
    menuTitle: string;
    cartTitle: string;
    addToCart: string;
    quantity: string;
    notes: string;
    notesPlaceholder: string;
    total: string;
    checkout: string;
    decrease: string;
    increase: string;
    emptyCart: string;
    itemAdded: string;
    placeOrder: string;
    placingOrder: string;
    orderSuccess: string;
    orderId: string;
    orderStatus: string;
    statusPlaced: string;
    statusBumped: string;
    statusCancelled: string;
    reconnecting: string;
    unavailable: string;
    allergenWarningTitle: string;
    allergenWarningDescription: string;
    allergenAckCheckbox: string;
    chatTitle: string;
    chatPlaceholder: string;
    chatSend: string;
    chatNotice: string;
    table: string;
    placedAt: string;
    items: string;
    backToMenu: string;
  };
  menu: {
    taxNote: string;
    pricesIncludeVat: string;
    chooseSize: string;
    from: string;
    serviceNotice: string;
  };
  bill: {
    /** Contains {billNo}. */
    paid: string;
    /** Contains {count}: pay-it-forward chai on the settled bill. */
    payForward: string;
  };
  pay: {
    button: string;
    subtotal: string;
    total: string;
    vatIncluded: string;
    service: string;
    choose: string;
    /** Contains {rate}. */
    taxRate: string;
    methods: Record<"cash" | "card" | "wallet" | "raast" | "bank_transfer", string>;
    labels: Record<"raast_id" | "jazzcash" | "easypaisa" | "iban" | "account_title", string>;
    /** Contains {name} and {qty}. */
    removed: string;
    /** Contains {total}. */
    cash: string;
    card: string;
    sent: string;
    /** Contains {total}. */
    payTo: string;
    sampleBanner: string;
    copy: string;
    copied: string;
    copyFailed: string;
    reference: string;
    invalidReference: string;
    paid: string;
    sending: string;
    networkError: string;
    noBill: string;
    /** Contains {total}, {rate} and {method}. */
    paidAmount: string;
    /** Contains {total}, {rate} and {method}: a settled bill whose prices included VAT. */
    paidVatIncluded: string;
    /** Contains {button}: the "I've paid" label, after the service changed on a transfer claim. */
    serviceChanged: string;
    cancelled: string;
    visitEnded: string;
  };
  counter: {
    /** Menu header on a counter QR. */
    header: string;
    /** Pay sheet title and the prompt under the pickup number. */
    payPrompt: string;
    pickupNumber: string;
    preparing: string;
    /** Contains {label}. */
    ready: string;
    collected: string;
    cancelled: string;
    /** Contains {total}. */
    cash: string;
    card: string;
  };
  call: {
    button: string;
    help: string;
    water: string;
    /** Used when the venue has no service_extra_label. */
    extra: string;
    called: string;
    resolved: string;
    /** Contains {seconds}. */
    wait: string;
    already: string;
    failed: string;
  };
  /** Ordering at a table: waiting for a waiter, the 4-digit number, and what happens after sending. */
  order: {
    waiting: string;
    thanks: string;
    numberTitle: string;
    numberHelp: string;
    /** Contains {n}. */
    numberDigit: string;
    numberWrong: string;
    tooManyTries: string;
    /** Contains {seconds}. */
    tryAgainIn: string;
    askWaiter: string;
    tooFast: string;
    tooBig: string;
    bigFirst: string;
    confirming: string;
    declined: string;
    unavailable: string;
    /** Contains {names}. */
    soldOut: string;
    failed: string;
  };
}
