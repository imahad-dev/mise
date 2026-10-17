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
}
