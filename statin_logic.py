ULN_CK = 200  # Example CK ULN (U/L)
ULN_ALT = 40  # Example ALT/AST ULN (U/L)
BILIRUBIN_THRESHOLD = 2.0  # mg/dL

def get_statin_recommendation(ck_value, transaminase, bilirubin, muscle_symptoms):
    """
    Evaluates clinical data and provides statin treatment recommendations.

    Args:
        ck_value (float): CK value in U/L.
        transaminase (float): ALT/AST value in U/L.
        bilirubin (float): Total Bilirubin value in mg/dL.
        muscle_symptoms (bool): True if muscle symptoms are present, False otherwise.

    Returns:
        str: The statin treatment recommendation.
    """
    result = ""

    # CK and myopathy assessment
    if ck_value > 10 * ULN_CK or (muscle_symptoms and ck_value > 10 * ULN_CK):
        result += "CK: Withdraw statin, hydrate, and monitor renal function.\n\n"
    elif 3 * ULN_CK < ck_value <= 10 * ULN_CK:
        result += "CK: Withdraw statin. Consider nonstatin-related causes and modify risk factors.\n\n"
    elif ck_value <= 3 * ULN_CK:
        if muscle_symptoms:
            result += (
                "CK: Withdraw statin. Consider nonstatin-related causes and modify risk factors.\n"
                "- If symptoms resolve and CK returns to normal: reinitiate statin at a reduced dose or switch to an alternative statin.\n"
                "- If CK remains elevated (>3x ULN) or symptoms persist: consult a specialist or consider muscle biopsy.\n\n"
            )
        else:
            result += (
                "CK: Continue statin. Follow up CK in 2–4 weeks. Consider nonstatin-related causes and modify risk factors.\n\n"
            )

    # Liver function assessment
    if transaminase <= ULN_ALT:
        result += "Liver: Start statin. Follow-up liver function test in 12 weeks.\n"
    elif ULN_ALT < transaminase <= 3 * ULN_ALT:
        if bilirubin <= BILIRUBIN_THRESHOLD:
            result += (
                "Liver: Consider starting statin. Reassess liver function and bilirubin in 2–4 weeks.\n"
            )
        else:
            result += "Liver: Do not start statin. Bilirubin > 2 mg/dL. Consult hepatic experts.\n"
    else:  # transaminase > 3x ULN
        result += "Liver: Do not start statin. Transaminase > 3× ULN. Consult hepatic experts.\n"

    return result.strip() # Remove trailing newlines if any