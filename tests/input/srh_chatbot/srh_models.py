from parsers.creation.datarowmodel import DataRowModel
from parsers.common.rowparser import ParserModel
from typing import List



## to keep
class GenderAnswerModel(ParserModel):
	question: str = ''
	answer_msg: List[str] = []

class AnswerRowModel(DataRowModel):
	NEUTRAL: GenderAnswerModel = GenderAnswerModel()
	FEMALE: GenderAnswerModel = GenderAnswerModel()
	MALE: GenderAnswerModel = GenderAnswerModel()
	prompt: List[str] = []
	external_links: str = '' #remove?
	NOTES_EO: str = '' #remove?

class NavigationQuestionModel(ParserModel):
	qst: str = ''
	child: str = ''
	has_answer: str = ''

class GenderModel(ParserModel):
	NEUTRAL: str = ''
	FEMALE: str = ''
	MALE: str = ''

class NavigationModel(DataRowModel):
	intro: GenderModel = GenderModel()
	top: str =''
	questions: List[NavigationQuestionModel] = []


class IDsInteractionModel(DataRowModel):
	NEUTRAL: str =''
	MALE: str =''
	FEMALE: str =''

class OptionModel(ParserModel):
	choice: str =''
	flow: str =''

class InteractionModel(DataRowModel):
	intro_message: str =''
	intro_question: str =''
	option: List[OptionModel] = []

class InteractionDispatcherModel(DataRowModel):
	top: str=''
	intro_message: str =''
	intro_question: str =''
	option: List[OptionModel] = []
	properties: List[str] = []










